#!/usr/bin/env python3
"""
Reczne sterowanie piecem ecoMAX 850P2 przez RS-485: wlacz / wylacz / kasuj alarm.

Wysyla dokladnie te same ramki, ktore wysyla panel ecoSTER (zaobserwowane):
  wlacz   0x71 [1]          68 0B 00 45 50 B0 07 71 01 B1 16   WYLACZONY -> CZYSZCZENIE
  wylacz  0x71 [2]          68 0B 00 45 50 B0 07 71 02 B2 16   ROZPALANIE -> WYGASZANIE
  kasuj   0x71 [3, kod, 0]  68 0D 00 45 50 B0 07 71 03 20 00 95 16 (kod 32)

NIC TUTAJ NIE URUCHAMIA SIE AUTOMATYCZNIE:
  * bez --wyslij skrypt tylko pokazuje stan i co by zrobil (nie dotyka portu ani uslugi),
  * --wyslij wymaga terminala i recznego wpisania TAK (nie zadziala z crona / HA / skryptu),
  * jedna ramka, nigdy nie ponawia,
  * sprawdza stan pieca dwa razy (z pliku parsera i na zywo z magistrali tuz przed nadaniem),
  * limity czasowe miedzy wysylkami,
  * na czas wysylki sam zatrzymuje usluge "piec" (port) i ZAWSZE ja przywraca - takze po bledzie i Ctrl+C.

Opis, ryzyka i procedura: narzedzia/README.md
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from functools import reduce

# --- konfiguracja -------------------------------------------------------------
PORT = "/dev/ttyUSB0"
BAUD = 115200
ODCZYTY = "/data/odczyty.json"
ODCZYTY_MAX_WIEK_S = 120
DZIENNIK = "/home/pi/piec_dane/sterowanie.log"
USLUGA = "piec"

ADRES_PIECA = 0x45
STAN_BAJT = 27
KOD_BAJT = 196
TYP_POLECENIA = 0x71
TYP_ODPOWIEDZI = 0xF1

# stany (bajt 27)
WYL, ROZP, PRACA, WYGAS, POSTOJ, RECZNA, ALARM, CZYSZ = 0, 1, 2, 4, 5, 6, 7, 8
NAZWY_STANOW = {WYL: "WYŁĄCZONY", ROZP: "ROZPALANIE", PRACA: "PRACA", WYGAS: "WYGASZANIE",
                POSTOJ: "POSTÓJ", RECZNA: "PRACA RĘCZNA", ALARM: "ALARM", CZYSZ: "CZYSZCZENIE"}
DOZWOLONE_KODY = {32}      # kody alarmow, ktore wolno kasowac (32 = nieudane rozpalenie)

# Polecenia. "grupa" laczy polecenia w jeden limit czasowy:
# wlacz i kasuj alarmu oba uruchamiaja rozpalanie, wiec maja wspolny limit.
POLECENIA = {
    "wlacz": {
        "dane": lambda kod: [1],
        "dozwolone_stany": {WYL},
        "sukces": lambda st: st not in (WYL, ALARM),
        "grupa": "rozpalanie", "limit_min": 30,
        "ostrzezenie": "Włączenie uruchamia czyszczenie i ROZPALANIE.\n"
                       "Upewnij się, że w zasobniku jest pellet, a palnik nie jest zalany niespalonym paliwem.",
    },
    "wylacz": {
        "dane": lambda kod: [2],
        "dozwolone_stany": {ROZP, PRACA, POSTOJ, RECZNA, CZYSZ},
        "sukces": lambda st: st in (WYGAS, WYL),
        "grupa": "wylacz", "limit_min": 2,
        "ostrzezenie": "Piec przejdzie w WYGASZANIE, a potem WYŁĄCZONY. Ogrzewanie przestanie działać.",
    },
    "kasuj": {
        "dane": lambda kod: [3, kod, 0],
        "dozwolone_stany": {ALARM},
        "sukces": lambda st: st != ALARM,
        "grupa": "rozpalanie", "limit_min": 30,
        "ostrzezenie": "Skasowanie alarmu nieudanego rozpalenia = KOLEJNA PRÓBA ROZPALENIA,\n"
                       "często z pelletem, który już leży w palniku. Po drugim nieudanym rozpaleniu idź do kotła.",
    },
}

# Pod jakim adresem nadajemy i kiedy (patrz README):
#   panel  - naglowek potwierdzony ramkami panelu (B0 07); nadajemy zaraz PO
#            odpowiedzi prawdziwego panelu, zeby nie nadawac jednoczesnie z nim
#   econet - pusty adres 0x56, nadajemy w jego okienku; naglowek 30 07 zgadniety
TOZSAMOSCI = {
    "panel":  {"adres": 0x50, "typ_nadawcy": 0xB0, "wersja": 0x07, "moment": "po_ramce_od_adresu"},
    "econet": {"adres": 0x56, "typ_nadawcy": 0x30, "wersja": 0x07, "moment": "po_zapytaniu_do_adresu"},
}
START, STOP = 0x68, 0x16


# --- ramki --------------------------------------------------------------------
def crc(bajty):
    return reduce(lambda a, b: a ^ b, bajty, 0)


def zbuduj_ramke(odbiorca, nadawca, typ_nadawcy, wersja, typ, dane):
    """68 | dl.L dl.H | odbiorca | nadawca | typ nadawcy | wersja | typ | dane | CRC | 16"""
    b = [START, 0, 0, odbiorca, nadawca, typ_nadawcy, wersja, typ] + list(dane)
    dl = len(b) + 2
    b[1], b[2] = dl & 0xFF, dl >> 8
    return b + [crc(b), STOP]


def hexy(b):
    return " ".join(f"{x:02X}" for x in b)


def nazwa(st):
    return NAZWY_STANOW.get(st, str(st))


class CzytnikRamek:
    """Ramki ze strumienia bajtow wg pola dlugosci + CRC + bajtu stopu."""

    def __init__(self, port):
        self.port = port
        self.buf = bytearray()

    def nastepna(self, timeout):
        koniec = time.monotonic() + timeout
        while time.monotonic() < koniec:
            r = self._wytnij()
            if r is not None:
                return r
            dane = self.port.read(64)
            if dane:
                self.buf.extend(dane)
        return None

    def _wytnij(self):
        while True:
            i = self.buf.find(bytes([START]))
            if i < 0:
                self.buf.clear()
                return None
            if i > 0:
                del self.buf[:i]
            if len(self.buf) < 3:
                return None
            dl = self.buf[1] | (self.buf[2] << 8)
            if not 10 <= dl <= 1024:
                del self.buf[0]
                continue
            if len(self.buf) < dl:
                return None
            r = list(self.buf[:dl])
            if r[-1] == STOP and crc(r[:-2]) == r[-2]:
                del self.buf[:dl]
                return r
            del self.buf[0]


# --- otoczenie (wydzielone, zeby dalo sie testowac) ------------------------------
def systemctl(akcja):
    try:
        out = subprocess.run(["systemctl", akcja, USLUGA], capture_output=True, text=True, timeout=30)
        return out.returncode, out.stdout.strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)


def usluga_aktywna():
    return systemctl("is-active")[1] == "active"


def otworz_port(sciezka):
    import serial
    return serial.Serial(sciezka, BAUD, bytesize=8, parity="N", stopbits=1, timeout=0.05, exclusive=True)


def czy_root():
    return os.geteuid() == 0


def potwierdzenie(pytanie):
    if not sys.stdin.isatty():
        print("Brak terminala - wysyłka wymaga ręcznego potwierdzenia. Przerywam.")
        return False
    return input(pytanie).strip() == "TAK"


def loguj(tekst):
    linia = f"{datetime.now().isoformat(timespec='seconds')} {tekst}"
    print(linia)
    try:
        os.makedirs(os.path.dirname(DZIENNIK), exist_ok=True)
        with open(DZIENNIK, "a", encoding="utf-8") as f:
            f.write(linia + "\n")
    except OSError as e:
        print(f"(nie udało się zapisać dziennika {DZIENNIK}: {e})")


def ostatnia_wysylka(grupa):
    """Czas ostatniej wysylki z danej grupy limitu (z dziennika)."""
    try:
        with open(DZIENNIK, encoding="utf-8") as f:
            linie = [l for l in f if f" WYSLANO grupa={grupa} " in l]
    except FileNotFoundError:
        return None
    if not linie:
        return None
    try:
        return datetime.fromisoformat(linie[-1].split(" ", 1)[0])
    except ValueError:
        return None


def stan_z_pliku():
    """(stan, kod, wiek_s) z odczyty.json parsera albo (None, None, None)."""
    try:
        with open(ODCZYTY, encoding="utf-8") as f:
            d = json.load(f)
        stan_txt = d["odczyty"]["stan"]
        kod = (d.get("alarm") or {}).get("kod")
        wiek = time.time() - datetime.fromisoformat(d["timestamp"]).timestamp()
    except (OSError, ValueError, KeyError, TypeError):
        return None, None, None
    odwrot = {v: k for k, v in NAZWY_STANOW.items()}
    return odwrot.get(stan_txt, stan_txt), kod, wiek


# --- magistrala ---------------------------------------------------------------
def czekaj_na_stan(czytnik, timeout):
    koniec = time.monotonic() + timeout
    while time.monotonic() < koniec:
        r = czytnik.nastepna(koniec - time.monotonic())
        if r is None:
            break
        if r[4] == ADRES_PIECA and r[7] == 0x08:
            m = r[7:-2]
            if len(m) > KOD_BAJT:
                return m[STAN_BAJT], m[KOD_BAJT]
    return None, None


def czekaj_na_moment(czytnik, toz, timeout):
    koniec = time.monotonic() + timeout
    while time.monotonic() < koniec:
        r = czytnik.nastepna(koniec - time.monotonic())
        if r is None:
            break
        if toz["moment"] == "po_zapytaniu_do_adresu" and r[4] == ADRES_PIECA and r[3] == toz["adres"]:
            return True
        if toz["moment"] == "po_ramce_od_adresu" and r[4] == toz["adres"]:
            return True
    return False


def obserwuj(czytnik, nasza, sekundy, sukces):
    wynik = {"echo": False, "odpowiedz_f1": False, "stany": [], "sukces": False}
    koniec = time.monotonic() + sekundy
    while time.monotonic() < koniec:
        r = czytnik.nastepna(koniec - time.monotonic())
        if r is None:
            break
        if r == nasza:
            wynik["echo"] = True
            continue
        if r[4] == ADRES_PIECA and r[7] == TYP_ODPOWIEDZI:
            wynik["odpowiedz_f1"] = True
            print(f"  <- odpowiedź pieca 0xF1: {hexy(r)}")
        if r[4] == ADRES_PIECA and r[7] == 0x08:
            m = r[7:-2]
            if len(m) > KOD_BAJT:
                st = (m[STAN_BAJT], m[KOD_BAJT])
                if not wynik["stany"] or wynik["stany"][-1] != st:
                    wynik["stany"].append(st)
                    print(f"  stan pieca: {nazwa(st[0])}, kod alarmu: {st[1]}")
                if sukces(st[0]):
                    wynik["sukces"] = True
                    break            # cel osiagniety - nie trzymaj portu dluzej
    return wynik


def sprawdz_warunki(polecenie, p, stan, kod, kod_arg):
    """Zwraca opis powodu odmowy albo None, gdy wolno."""
    if stan not in p["dozwolone_stany"]:
        dozw = ", ".join(nazwa(s) for s in sorted(p["dozwolone_stany"]))
        return f"Piec jest w stanie {nazwa(stan)}; '{polecenie}' wolno tylko w: {dozw}."
    if polecenie == "kasuj" and kod != kod_arg:
        return f"Aktywny alarm ma kod {kod}, a podano --kod {kod_arg}."
    if polecenie == "wlacz" and kod not in (0, None):
        return f"Jest aktywny kod alarmu {kod}. Najpierw 'kasuj'."
    return None


# --- glowna logika -----------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description="Ręczne sterowanie piecem (eksperymentalne). "
                                             "Bez --wyslij nic nie jest wysyłane.")
    ap.add_argument("polecenie", choices=sorted(POLECENIA))
    ap.add_argument("--kod", type=int, help="kod alarmu (wymagany dla 'kasuj'), np. 32")
    ap.add_argument("--wyslij", action="store_true", help="naprawdę wyślij (wymaga sudo i wpisania TAK)")
    ap.add_argument("--jako", choices=sorted(TOZSAMOSCI), default="panel")
    ap.add_argument("--port", default=PORT)
    ap.add_argument("--obserwuj", type=int, default=60, help="maks. sekund obserwacji po wysłaniu")
    a = ap.parse_args(argv)

    p = POLECENIA[a.polecenie]
    if a.polecenie == "kasuj":
        if a.kod is None:
            ap.error("'kasuj' wymaga --kod, np. --kod 32")
        if a.kod not in DOZWOLONE_KODY:
            print(f"Kod {a.kod} nie jest na liście DOZWOLONE_KODY {sorted(DOZWOLONE_KODY)}. Przerywam.")
            return 2
    toz = TOZSAMOSCI[a.jako]
    ramka = zbuduj_ramke(ADRES_PIECA, toz["adres"], toz["typ_nadawcy"], toz["wersja"],
                         TYP_POLECENIA, p["dane"](a.kod))
    print(f"Polecenie: {a.polecenie}  jako {a.jako} (0x{toz['adres']:02X})")
    print(f"Ramka:     {hexy(ramka)}")

    # 1) stan z pliku parsera - bez dotykania portu i uslugi
    stan, kod, wiek = stan_z_pliku()
    if stan is None:
        print(f"Nie można odczytać {ODCZYTY} (czy usługa '{USLUGA}' działa?). Przerywam.")
        return 3
    if wiek > ODCZYTY_MAX_WIEK_S:
        print(f"Dane w {ODCZYTY} są sprzed {wiek:.0f} s - parser nie działa? Przerywam.")
        return 3
    print(f"Piec teraz: {nazwa(stan)}, kod alarmu: {kod}  (odczyt sprzed {wiek:.0f} s)")
    odmowa = sprawdz_warunki(a.polecenie, p, stan, kod, a.kod)
    if odmowa:
        print(odmowa + " Nic nie wysyłam.")
        return 3

    ost = ostatnia_wysylka(p["grupa"])
    if ost is not None and (datetime.now() - ost).total_seconds() < p["limit_min"] * 60:
        print(f"Ostatnia wysyłka z grupy '{p['grupa']}': {ost}. "
              f"Limit: jedna na {p['limit_min']} min. Przerywam.")
        return 4

    if not a.wyslij:
        print("\nTryb podglądu: warunki spełnione, NIC nie zostało wysłane.\n"
              f"Aby wysłać: sudo python3 {sys.argv[0]} {a.polecenie}"
              f"{' --kod ' + str(a.kod) if a.kod is not None else ''} --wyslij")
        return 0

    if not czy_root():
        print("Wysyłka wymaga sudo (port i zatrzymanie usługi). Przerywam.")
        return 2
    print("\nUWAGA: " + p["ostrzezenie"])
    print(f"Na czas wysyłki (do ok. {a.obserwuj + 30} s) usługa '{USLUGA}' zostanie zatrzymana "
          "i potem uruchomiona ponownie.")
    if not potwierdzenie(f"Wpisz TAK, aby wysłać '{a.polecenie}': "):
        print("Nie potwierdzono. Nic nie wysłano.")
        return 5

    # 2) zatrzymanie uslugi i praca na porcie - przywrocenie uslugi ZAWSZE w finally
    byla_aktywna = usluga_aktywna()
    port = None
    try:
        if byla_aktywna:
            rc, txt = systemctl("stop")
            if rc != 0:
                print(f"Nie udało się zatrzymać usługi '{USLUGA}': {txt}. Nic nie wysłano.")
                return 2
            time.sleep(1)
        try:
            port = otworz_port(a.port)
        except Exception as e:
            print(f"Nie można otworzyć {a.port}: {e}. Nic nie wysłano.")
            return 2
        czytnik = CzytnikRamek(port)

        stan, kod = czekaj_na_stan(czytnik, 15)
        if stan is None:
            print("Brak ramki stanu od pieca w 15 s. Nic nie wysłano.")
            return 3
        odmowa = sprawdz_warunki(a.polecenie, p, stan, kod, a.kod)
        if odmowa:
            print("Stan zmienił się w międzyczasie: " + odmowa + " Nic nie wysłano.")
            return 3

        print("Czekam na wolne okienko na magistrali...")
        if not czekaj_na_moment(czytnik, toz, 10):
            print("Nie doczekałem się momentu nadania w 10 s. Nic nie wysłano.")
            return 6
        port.write(bytes(ramka))
        port.flush()
        loguj(f"WYSLANO grupa={p['grupa']} polecenie={a.polecenie} jako={a.jako} "
              f"stan_przed={nazwa(stan)} kod={kod}: {hexy(ramka)}")

        print(f"Obserwuję magistralę (maks. {a.obserwuj} s)...")
        w = obserwuj(czytnik, ramka, a.obserwuj, p["sukces"])
        loguj(f"WYNIK polecenie={a.polecenie} echo={w['echo']} odpowiedz_F1={w['odpowiedz_f1']} "
              f"stany={[(nazwa(s), k) for s, k in w['stany']]} sukces={w['sukces']}")
        if w["sukces"]:
            print(f"\nOK: '{a.polecenie}' przyjęte, piec: {nazwa(w['stany'][-1][0])}.")
            return 0
        print(f"\nBrak oczekiwanej zmiany stanu po '{a.polecenie}'. NIE ponawiam - sprawdź README.")
        return 7
    finally:
        if port is not None:
            try:
                port.close()
            except Exception:
                pass
        if byla_aktywna:
            rc, txt = systemctl("start")
            time.sleep(1)
            if usluga_aktywna():
                print(f"Usługa '{USLUGA}' uruchomiona ponownie.")
            else:
                print(f"!!! Usługa '{USLUGA}' NIE wystartowała ({txt}). Uruchom ręcznie: "
                      f"sudo systemctl start {USLUGA}")


if __name__ == "__main__":
    sys.exit(main())
