#!/usr/bin/env python3
"""
Reczne sterowanie piecem ecoMAX 850P2 przez RS-485: wlacz / wylacz / kasuj alarm.

Wysyla dokladnie te same ramki, ktore wysyla panel ecoSTER (zaobserwowane):
  wlacz   0x71 [1]          68 0B 00 45 50 B0 07 71 01 B1 16   WYLACZONY -> CZYSZCZENIE
  wylacz  0x71 [2]          68 0B 00 45 50 B0 07 71 02 B2 16   ROZPALANIE -> WYGASZANIE
  kasuj   0x71 [3, kod, 0]  68 0D 00 45 50 B0 07 71 03 20 00 95 16 (kod 32)  ALARM -> CZYSZCZENIE
                            (zlapane z panelu 2 razy: 04.10 i 10.11.2026)

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
        "dozwolone_stany": {WYL, WYGAS},      # z WYGASZANIA panel tez wlacza (06.11.2026 16:32)
        "sukces": lambda st: st not in (WYL, WYGAS, ALARM),
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
        "ostrzezenie": "Alarm 32 = „Nieudana próba rozpalenia kotła”. Skasowanie = KOLEJNE ROZPALANIE\n"
                       "(do 3 prób po ok. 6,5 min, przy każdej dawka paliwa),\n"
                       "często z pelletem, który już leży w palniku. Po drugim nieudanym rozpaleniu idź do kotła.",
    },
}

# Pod jakim adresem nadajemy i w ktorym okienku (patrz README).
# Cykl pieca (z logu, ok. 1,2 raza na sekunde):
#   45>51:40, [45>57:40, 45>58:40 co 4. cykl], 45>56:30, 45>55:0A, 45>00:08, 45>50:0A, 50>00:89
# Po zapytaniu do nieobecnego adresu (0x51, 0x55, 0x56...) piec czeka chwile na odpowiedz -
# to jest puste okienko, w ktorym nikt inny nie nadaje.
#   panel    - adres i naglowek panelu (potwierdzone, piec przyjmuje od niego 0x71), nadane
#              w pustym okienku adresu 0x55 -> bez kolizji z prawdziwym panelem. DOMYSLNE.
#   panel-po - jak panel, ale zaraz PO ramce prawdziwego panelu (ryzyko kolizji z pieciem)
#   panel2   - adres 0x55 (piec odpytuje go tym samym 0x0A co panel - pewnie "drugi panel"),
#              we wlasnym okienku; naglowek jak panel
#   econet   - adres 0x56 we wlasnym okienku; naglowek 30 07 zgadniety
# "okienko" = adres, po zapytaniu do ktorego nadajemy; None = po ramce OD naszego adresu.
TOZSAMOSCI = {
    "panel":    {"adres": 0x50, "typ_nadawcy": 0xB0, "wersja": 0x07, "okienko": 0x55},
    "panel-po": {"adres": 0x50, "typ_nadawcy": 0xB0, "wersja": 0x07, "okienko": None},
    "panel2":   {"adres": 0x55, "typ_nadawcy": 0xB0, "wersja": 0x07, "okienko": 0x55},
    "econet":   {"adres": 0x56, "typ_nadawcy": 0x30, "wersja": 0x07, "okienko": 0x56},
}
MIN_ODSTEP_S = 60            # min. odstep miedzy dowolnymi wysylkami (takze nieprzyjetymi)
ALARMY = "/home/pi/piec_dane/alarmy"
POLECENIA_PLIK = "/home/pi/piec_dane/polecenia.jsonl"
ALARMY_OKNO_H = 3            # ile godzin wstecz liczymy alarmy
ALARMY_MAX = 1               # przy wiekszej liczbie alarmow w oknie: odmowa wlacz/kasuj
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


def ostatnie_wysylki(grupa):
    """(czas ostatniej PRZYJETEJ wysylki z grupy, czas ostatniej jakiejkolwiek wysylki).
    Przyjeta = piec odpowiedzial 0xF1 albo zmienil stan. Wysylka bez wpisu WYNIK
    (np. przerwana) liczy sie ostroznie jako przyjeta."""
    przyjeta = dowolna = None
    oczekuje = None          # (czas, grupa) WYSLANO bez WYNIK
    try:
        with open(DZIENNIK, encoding="utf-8") as f:
            for l in f:
                try:
                    t = datetime.fromisoformat(l.split(" ", 1)[0])
                except ValueError:
                    continue
                if " WYSLANO grupa=" in l:
                    if oczekuje and oczekuje[1] == grupa:
                        przyjeta = oczekuje[0]
                    oczekuje = (t, l.split(" WYSLANO grupa=", 1)[1].split(" ", 1)[0])
                    dowolna = t
                elif " WYNIK " in l and oczekuje:
                    if oczekuje[1] == grupa and "przyjete=False" not in l:
                        przyjeta = oczekuje[0]
                    oczekuje = None
    except FileNotFoundError:
        return None, None
    if oczekuje and oczekuje[1] == grupa:
        przyjeta = oczekuje[0]
    return przyjeta, dowolna


def alarmy_w_oknie():
    """Liczba alarmow (plikow parsera) z ostatnich ALARMY_OKNO_H godzin."""
    n = 0
    try:
        pliki = [x for x in os.listdir(ALARMY) if x.startswith("alarm_") and x.endswith(".json")]
    except OSError:
        return 0
    for x in pliki:
        try:
            t = datetime.strptime(x[6:25], "%Y-%m-%d_%H-%M-%S")
        except ValueError:
            continue
        if 0 <= (datetime.now() - t).total_seconds() <= ALARMY_OKNO_H * 3600:
            n += 1
    return n


def dopisz_polecenie(polecenie, jako, ramka, stan_przed, kod_przed, wynik):
    """Wpis do polecenia.jsonl parsera - zeby wysylka byla w historii i poszla na MQTT
    (parser jest w tym czasie zatrzymany i sam jej nie zobaczy)."""
    opisy = {"wlacz": ("włączenie pieca (sterowanie.py)", "wlaczenie"),
             "wylacz": ("wyłączenie pieca (sterowanie.py)", "wylaczenie"),
             "kasuj": (f"kasowanie alarmu {kod_przed} (sterowanie.py)", "kasowanie_alarmu")}
    stan_po = wynik["stany"][-1] if wynik["stany"] else (None, None)
    rek = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "nadawca": f"0x{ramka[4]:02X}", "odbiorca": f"0x{ramka[3]:02X}", "typ": f"0x{ramka[7]:02X}",
        "rodzaj": opisy[polecenie][1], "opis": opisy[polecenie][0],
        "zrodlo": "sterowanie.py", "jako": jako,
        "echo": wynik["echo"], "odpowiedz_f1": wynik["odpowiedz_f1"], "sukces": wynik["sukces"],
        "stan_przed": nazwa(stan_przed), "alarm_kod_przed": kod_przed,
        "stan_po": nazwa(stan_po[0]) if stan_po[0] is not None else None, "alarm_kod_po": stan_po[1],
        "ramka": ramka[7:-2], "ramka_pelna": ramka,
    }
    try:
        with open(POLECENIA_PLIK, "a", encoding="utf-8") as f:
            f.write(json.dumps(rek, ensure_ascii=False) + "\n")
    except OSError as e:
        print(f"(nie udało się dopisać do {POLECENIA_PLIK}: {e})")


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
        if toz["okienko"] is not None and r[4] == ADRES_PIECA and r[3] == toz["okienko"]:
            return True
        if toz["okienko"] is None and r[4] == toz["adres"]:
            return True
    return False


def obserwuj(czytnik, nasza, sekundy, sukces):
    wynik = {"echo": False, "odpowiedz_f1": False, "stany": [], "sukces": False}
    start = time.monotonic()
    koniec = start + sekundy
    while time.monotonic() < koniec:
        r = czytnik.nastepna(koniec - time.monotonic())
        if r is None:
            break
        if r == nasza:
            wynik["echo"] = True
            continue
        # piec odpowiada 0xF1 w tej samej sekundzie; brak odpowiedzi po 10 s = nie przyjal
        if not wynik["odpowiedz_f1"] and time.monotonic() - start > 10:
            break
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

    if p["grupa"] == "rozpalanie":
        n = alarmy_w_oknie()
        if n > ALARMY_MAX:
            print(f"W ostatnich {ALARMY_OKNO_H} h było {n} alarmów. Kolejne zdalne rozpalanie "
                  "jest zablokowane - trzeba sprawdzić palnik przy kotle. Nic nie wysyłam.")
            return 4

    przyjeta, dowolna = ostatnie_wysylki(p["grupa"])
    if przyjeta is not None and (datetime.now() - przyjeta).total_seconds() < p["limit_min"] * 60:
        print(f"Ostatnia przyjęta wysyłka z grupy '{p['grupa']}': {przyjeta}. "
              f"Limit: jedna na {p['limit_min']} min. Przerywam.")
        return 4
    if dowolna is not None and (datetime.now() - dowolna).total_seconds() < MIN_ODSTEP_S:
        print(f"Ostatnia wysyłka: {dowolna}. Odczekaj {MIN_ODSTEP_S} s między próbami. Przerywam.")
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
        przyjete = w["odpowiedz_f1"] or w["sukces"]
        loguj(f"WYNIK polecenie={a.polecenie} echo={w['echo']} odpowiedz_F1={w['odpowiedz_f1']} "
              f"stany={[(nazwa(s), k) for s, k in w['stany']]} sukces={w['sukces']} przyjete={przyjete}")
        dopisz_polecenie(a.polecenie, a.jako, ramka, stan, kod, w)
        if w["sukces"]:
            print(f"\nOK: '{a.polecenie}' przyjęte, piec: {nazwa(w['stany'][-1][0])}.")
            return 0
        if not przyjete:
            inne = [k for k in TOZSAMOSCI if k != a.jako]
            print(f"\nPiec nie odpowiedział na '{a.polecenie}' (echo={w['echo']}). Nie ponawiam sam.\n"
                  f"Ta próba nie zużywa limitu - po {MIN_ODSTEP_S} s możesz spróbować innego wariantu: "
                  + ", ".join(f"--jako {k}" for k in inne))
            return 7
        print(f"\nPiec potwierdził '{a.polecenie}' (0xF1), ale stan się nie zmienił. NIE ponawiam - sprawdź README.")
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
