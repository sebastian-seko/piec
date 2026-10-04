#!/usr/bin/env python3
"""
Reczne kasowanie alarmu ecoMAX 850P2 przez magistrale RS-485.

NARZEDZIE EKSPERYMENTALNE. Nic tutaj nie uruchamia sie automatycznie:
  * bez flagi --wyslij skrypt tylko slucha i pokazuje, co by zrobil,
  * z --wyslij wymaga terminala i recznego wpisania TAK (nie zadziala z crona/skryptu),
  * wysyla dokladnie jedna ramke, nigdy nie ponawia,
  * odmawia, gdy piec nie jest w ALARM z podanym kodem albo kod nie jest na liscie,
  * odmawia, gdy od ostatniego wyslania minelo mniej niz LIMIT_MINUT,
  * odmawia, gdy dziala usluga "piec" (dwa procesy na jednym porcie psuja odczyt).

Szczegoly, ryzyka i procedura: narzedzia/README.md
"""

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime
from functools import reduce

# --- konfiguracja -------------------------------------------------------------
PORT = "/dev/ttyUSB0"
BAUD = 115200

ADRES_PIECA = 0x45
STAN_BAJT = 27            # bajt stanu w ramce 0x08 (7 = ALARM)
KOD_BAJT = 196            # bajt kodu alarmu w ramce 0x08
STAN_ALARM = 7

# Kody, dla ktorych w ogole wolno wyslac kasowanie. Dopisuj swiadomie.
DOZWOLONE_KODY = {32}     # 32 = prawdopodobnie "nieudane rozpalenie"

LIMIT_MINUT = 60          # min. odstep miedzy wysylkami (zapisywany w dzienniku)
DZIENNIK = "/home/pi/piec_dane/kasowanie_alarmu.log"

# Tozsamosc, pod ktora wysylamy, i moment nadania (patrz README):
#   panel  - podszycie sie pod panel ecoSTER (0x50); nadajemy zaraz PO tym, jak
#            prawdziwy panel skonczy swoja odpowiedz, zeby nie nadawac jednoczesnie.
#   econet - adres modulu ecoNET (0x56), ktorego u Ciebie nie ma; piec go odpytuje
#            (typ 0x30) i nikt nie odpowiada, wiec nadajemy w tym pustym okienku.
# Bajty typu nadawcy i wersji: dla panelu zaobserwowane (0xB0, 0x07);
# dla ecoNET zgadniete (0x30 z oryginalnego kodu econetanalyze, wersja 0x07).
TOZSAMOSCI = {
    "panel":  {"adres": 0x50, "typ_nadawcy": 0xB0, "wersja": 0x07, "moment": "po_ramce_od_adresu"},
    "econet": {"adres": 0x56, "typ_nadawcy": 0x30, "wersja": 0x07, "moment": "po_zapytaniu_do_adresu"},
}

TYP_POLECENIA = 0x71
TYP_ODPOWIEDZI = 0xF1
POLECENIE_KASUJ = 3       # dane ramki 0x71: [3, kod, 0]

START, STOP = 0x68, 0x16
NAZWY_STANOW = {0: "WYŁĄCZONY", 1: "ROZPALANIE", 2: "PRACA", 4: "WYGASZANIE", 5: "POSTÓJ",
                6: "PRACA RĘCZNA", 7: "ALARM", 8: "CZYSZCZENIE"}


# --- ramki --------------------------------------------------------------------
def crc(bajty):
    return reduce(lambda a, b: a ^ b, bajty, 0)


def zbuduj_ramke(odbiorca, nadawca, typ_nadawcy, wersja, typ, dane):
    """68 | dl.L dl.H | odbiorca | nadawca | typ nadawcy | wersja | typ | dane | CRC | 16
    dlugosc = cala ramka; CRC = XOR wszystkich bajtow przed CRC (wlacznie z 0x68)."""
    b = [START, 0, 0, odbiorca, nadawca, typ_nadawcy, wersja, typ] + list(dane)
    dl = len(b) + 2
    b[1], b[2] = dl & 0xFF, dl >> 8
    return b + [crc(b), STOP]


def hexy(b):
    return " ".join(f"{x:02X}" for x in b)


class CzytnikRamek:
    """Skladanie ramek ze strumienia bajtow wg pola dlugosci + CRC + bajtu stopu."""

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
            del self.buf[0]          # falszywy start - szukaj dalej


def opis_ramki(r):
    return {"odbiorca": r[3], "nadawca": r[4], "typ": r[7], "dane": r[8:-2]}


# --- bezpieczniki ---------------------------------------------------------------
def usluga_aktywna():
    try:
        out = subprocess.run(["systemctl", "is-active", "piec"], capture_output=True, text=True)
        return out.stdout.strip() == "active"
    except (OSError, FileNotFoundError):
        return False


def otworz_port(sciezka):
    import serial
    return serial.Serial(sciezka, BAUD, bytesize=8, parity="N", stopbits=1,
                         timeout=0.05, exclusive=True)


def loguj(tekst):
    linia = f"{datetime.now().isoformat(timespec='seconds')} {tekst}"
    print(linia)
    try:
        os.makedirs(os.path.dirname(DZIENNIK), exist_ok=True)
        with open(DZIENNIK, "a", encoding="utf-8") as f:
            f.write(linia + "\n")
    except OSError as e:
        print(f"(nie udało się zapisać dziennika {DZIENNIK}: {e})")


def ostatnia_wysylka():
    try:
        with open(DZIENNIK, encoding="utf-8") as f:
            linie = [l for l in f if " WYSLANO " in l]
    except FileNotFoundError:
        return None
    if not linie:
        return None
    try:
        return datetime.fromisoformat(linie[-1].split(" ", 1)[0])
    except ValueError:
        return None


def potwierdzenie(pytanie):
    if not sys.stdin.isatty():
        print("Brak terminala - wysyłka wymaga ręcznego potwierdzenia. Przerywam.")
        return False
    return input(pytanie).strip() == "TAK"


# --- glowna logika -----------------------------------------------------------
def czekaj_na_stan(czytnik, timeout):
    """Zwraca (stan, kod) z pierwszej ramki 0x08 od pieca albo (None, None)."""
    koniec = time.monotonic() + timeout
    while time.monotonic() < koniec:
        r = czytnik.nastepna(koniec - time.monotonic())
        if r is None:
            break
        o = opis_ramki(r)
        if o["nadawca"] == ADRES_PIECA and o["typ"] == 0x08:
            m = r[7:-2]          # tresc jak w parserze: m[0] = typ ramki
            if len(m) > KOD_BAJT:
                return m[STAN_BAJT], m[KOD_BAJT]
    return None, None


def czekaj_na_moment(czytnik, toz, timeout):
    """Czeka na chwile, w ktorej mozna nadac (patrz TOZSAMOSCI['moment'])."""
    koniec = time.monotonic() + timeout
    while time.monotonic() < koniec:
        r = czytnik.nastepna(koniec - time.monotonic())
        if r is None:
            break
        o = opis_ramki(r)
        if toz["moment"] == "po_zapytaniu_do_adresu":
            if o["nadawca"] == ADRES_PIECA and o["odbiorca"] == toz["adres"]:
                return True
        elif toz["moment"] == "po_ramce_od_adresu":
            if o["nadawca"] == toz["adres"]:
                return True
    return False


def obserwuj(czytnik, nasza, sekundy):
    """Po wyslaniu: czy przyszla odpowiedz 0xF1 i jak zmienil sie stan pieca."""
    wynik = {"echo": False, "odpowiedz_f1": False, "stany": []}
    koniec = time.monotonic() + sekundy
    while time.monotonic() < koniec:
        r = czytnik.nastepna(koniec - time.monotonic())
        if r is None:
            break
        if r == nasza:
            wynik["echo"] = True
            continue
        o = opis_ramki(r)
        if o["nadawca"] == ADRES_PIECA and o["typ"] == TYP_ODPOWIEDZI:
            wynik["odpowiedz_f1"] = True
            print(f"  <- odpowiedź pieca 0xF1: {hexy(r)}")
        if o["nadawca"] == ADRES_PIECA and o["typ"] == 0x08:
            m = r[7:-2]
            if len(m) > KOD_BAJT:
                st = (m[STAN_BAJT], m[KOD_BAJT])
                if not wynik["stany"] or wynik["stany"][-1] != st:
                    wynik["stany"].append(st)
                    print(f"  stan pieca: {NAZWY_STANOW.get(st[0], st[0])}, kod alarmu: {st[1]}")
    return wynik


def main(argv=None):
    ap = argparse.ArgumentParser(description="Ręczne kasowanie alarmu ecoMAX (eksperymentalne). "
                                             "Bez --wyslij nic nie jest wysyłane.")
    ap.add_argument("--kod", type=int, required=True, help="kod alarmu do skasowania, np. 32")
    ap.add_argument("--jako", choices=sorted(TOZSAMOSCI), default="panel",
                    help="pod jakim adresem nadać (domyślnie: panel)")
    ap.add_argument("--wyslij", action="store_true", help="naprawdę wyślij (wymaga wpisania TAK)")
    ap.add_argument("--tylko-ramka", action="store_true", help="tylko pokaż bajty ramki, nie otwieraj portu")
    ap.add_argument("--port", default=PORT)
    ap.add_argument("--obserwuj", type=int, default=30, help="ile sekund obserwować po wysłaniu")
    a = ap.parse_args(argv)

    toz = TOZSAMOSCI[a.jako]
    ramka = zbuduj_ramke(ADRES_PIECA, toz["adres"], toz["typ_nadawcy"], toz["wersja"],
                         TYP_POLECENIA, [POLECENIE_KASUJ, a.kod, 0])
    print(f"Ramka kasowania alarmu {a.kod} jako {a.jako} (0x{toz['adres']:02X}):")
    print(f"  {hexy(ramka)}")
    if a.tylko_ramka:
        return 0

    if a.kod not in DOZWOLONE_KODY:
        print(f"Kod {a.kod} nie jest na liście DOZWOLONE_KODY {sorted(DOZWOLONE_KODY)}. Przerywam.")
        return 2
    if usluga_aktywna():
        print("Usługa 'piec' działa i trzyma port. Zatrzymaj ją ręcznie:\n"
              "  sudo systemctl stop piec\n"
              "a po zakończeniu uruchom ponownie:\n"
              "  sudo systemctl start piec")
        return 2

    try:
        port = otworz_port(a.port)
    except Exception as e:
        print(f"Nie można otworzyć {a.port}: {e}")
        return 2
    czytnik = CzytnikRamek(port)
    try:
        print("Nasłuchuję stanu pieca...")
        stan, kod = czekaj_na_stan(czytnik, 15)
        if stan is None:
            print("Brak ramki 0x08 od pieca w ciągu 15 s. Przerywam.")
            return 3
        print(f"Piec: {NAZWY_STANOW.get(stan, stan)}, kod alarmu: {kod}")
        if stan != STAN_ALARM or kod != a.kod:
            print(f"Piec nie jest w ALARM z kodem {a.kod}. Nic nie wysyłam.")
            return 3

        if not a.wyslij:
            print("\nTryb podglądu (bez --wyslij): warunki spełnione, ale NIC nie zostało wysłane.")
            return 0

        ost = ostatnia_wysylka()
        if ost is not None and (datetime.now() - ost).total_seconds() < LIMIT_MINUT * 60:
            print(f"Ostatnia wysyłka: {ost}. Limit to jedna na {LIMIT_MINUT} min. Przerywam.")
            return 4

        print("\nUWAGA: kasowanie nieudanego rozpalenia uruchamia kolejną próbę rozpalenia.\n"
              "Przed wysłaniem sprawdź palnik: czy nie ma w nim nadmiaru niespalonego pelletu.")
        if not potwierdzenie(f"Wpisz TAK, aby wysłać jedną ramkę kasowania alarmu {a.kod}: "):
            print("Nie potwierdzono. Nic nie wysłano.")
            return 5

        # Podczas potwierdzania w buforze zebraly sie stare ramki - odrzuc je
        # i sprawdz stan jeszcze raz na swiezych danych tuz przed nadaniem.
        port.reset_input_buffer()
        czytnik.buf.clear()
        stan, kod = czekaj_na_stan(czytnik, 15)
        if stan != STAN_ALARM or kod != a.kod:
            print(f"Stan zmienił się w międzyczasie ({NAZWY_STANOW.get(stan, stan)}, kod {kod}). "
                  "Nic nie wysyłam.")
            return 3

        print("Czekam na wolne okienko na magistrali...")
        if not czekaj_na_moment(czytnik, toz, 10):
            print("Nie doczekałem się momentu nadania w 10 s. Nic nie wysłano.")
            return 6
        port.write(bytes(ramka))
        port.flush()
        loguj(f"WYSLANO kasowanie alarmu {a.kod} jako {a.jako}: {hexy(ramka)}")

        print(f"Obserwuję magistralę przez {a.obserwuj} s...")
        w = obserwuj(czytnik, ramka, a.obserwuj)
        skasowany = any(s[0] != STAN_ALARM for s in w["stany"])
        loguj(f"WYNIK echo={w['echo']} odpowiedz_F1={w['odpowiedz_f1']} "
              f"stany={[(NAZWY_STANOW.get(s, s), k) for s, k in w['stany']]} "
              f"alarm_skasowany={skasowany}")
        print("\nAlarm skasowany." if skasowany else
              "\nPiec nadal w alarmie (albo brak ramek). NIE ponawiam - sprawdź README.")
        return 0 if skasowany else 7
    finally:
        port.close()
        print("\nPamiętaj uruchomić usługę: sudo systemctl start piec")


if __name__ == "__main__":
    sys.exit(main())
