# Analizator EcoNet
# (C) 2020 Tomasz Król https://github.com/twkrol/econetanalyze
# Gwarancji żadnej nie daję. Ale można korzystać do woli i modyfikować wg potrzeb

import functools
import json
import math
import os
import socket
import struct
import sys
import time
from datetime import datetime

import signal

import serial
import ecoster
import ecomax850p2 as ecomax


#ŹRÓDŁO DANYCH
# SOURCE = 'FILE'
filePATH = "/data/raw.txt"

#SOURCE = 'STREAM'
streamIP = '192.168.99.158'
streamPORT = 23

SOURCE = 'SERIAL'
serialPORT = '/dev/ttyUSB0'
serialBAUDRATE = 115200


#########################################################################
# START ANALIZY
#########################################################################

RAMKA_START = 0x68
RAMKA_STOP = 0x16
NADAWCA_ECONET = 0x56
NADAWCA_ECOMAX = 0x45
NADAWCA_ECOSTER = 0x50
NADAWCA_TYP_ECONET = 0x30

RAMKA_INFO_STEROWNIKA = 0x08
RAMKA_INFO_PANELU = 0x89

# Ramki obslugiwane przez parsery: (nadawca, typ ramki)
ZNANE_RAMKI = {
    (NADAWCA_ECOMAX, RAMKA_INFO_STEROWNIKA),
    (NADAWCA_ECOSTER, RAMKA_INFO_PANELU),
}

# Nieznane ramki - ostatnia ramka dla kazdej kombinacji nadawca/odbiorca/typ.
# /data to tmpfs 1 MB, wiec trzymamy tylko najnowsza ramke per rodzaj i limit wpisow.
NIEZNANE_PLIK = "/data/nieznane.json"
NIEZNANE_LIMIT = 32
nieznane = {}


def zapisz_nieznana(ramka, message):
    nadawca = ramka[ADRES_NADAWCY_BYTE]
    odbiorca = ramka[ADRES_ODBIORCY_BYTE]
    typ = ramka[TYP_RAMKI]
    klucz = f"nadawca_0x{nadawca:02X}_odbiorca_0x{odbiorca:02X}_typ_0x{typ:02X}"
    teraz = datetime.now().isoformat(timespec="seconds")

    wpis = nieznane.get(klucz)
    if wpis is None:
        if len(nieznane) >= NIEZNANE_LIMIT:
            # wyrzuc najdawniej widziany rodzaj ramki
            najstarszy = min(nieznane, key=lambda k: nieznane[k]["ostatnio"])
            del nieznane[najstarszy]
        wpis = {
            "nadawca": f"0x{nadawca:02X}",
            "odbiorca": f"0x{odbiorca:02X}",
            "typ": f"0x{typ:02X}",
            "licznik": 0,
            "pierwszy_raz": teraz,
        }
        nieznane[klucz] = wpis

    wpis["licznik"] += 1
    wpis["ostatnio"] = teraz
    wpis["dlugosc"] = len(message)
    wpis["ramka"] = list(message)
    wpis["ramka_pelna"] = list(ramka)   # z naglowkiem, CRC i bajtem stopu

    tmp = NIEZNANE_PLIK + ".tmp"
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(nieznane, f, ensure_ascii=False, indent=2)
        os.replace(tmp, NIEZNANE_PLIK)
    except (OSError, TypeError, ValueError) as e:
        print(f"Błąd zapisu pliku {NIEZNANE_PLIK}: {e}")

try:
    SOURCE
except NameError:
    print("Nie wybrano źródła danych! Popraw konfigurację na początku tego pliku.")
    exit()


def open_source():
    if SOURCE == 'FILE':
        try:
            f = open(filePATH, 'rb')
            print(f"Plik {filePATH} został otwarty")
            return f
        except OSError as e:
            print(f"Błąd otwarcia pliku {filePATH}: {e}")
            exit()

    elif SOURCE == 'STREAM':
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((streamIP, streamPORT))
            print(f"Port {streamPORT} pod adresem {streamIP} został otwarty")
            return s
        except OSError as e:
            print(f"Błąd połączenia z {streamIP}:{streamPORT}: {e}")
            exit()

    elif SOURCE == 'SERIAL':
        try:
            ser = serial.Serial(serialPORT, serialBAUDRATE)
            ser.bytesize = serial.EIGHTBITS
            ser.parity = serial.PARITY_NONE
            ser.stopbits = serial.STOPBITS_ONE
            print(f"Port {serialPORT} został otwarty")
            return ser
        except serial.SerialException as e:
            print(f"Błąd otwarcia portu {serialPORT}: {e}")
            exit()

    else:
        print("Nieznany typ źródła danych. Popraw konfigurację na początku tego pliku.")
        exit()


def reopen_serial():
    while True:
        print(f"Próba ponownego połączenia z {serialPORT}...")
        time.sleep(5)
        try:
            ser = serial.Serial(serialPORT, serialBAUDRATE)
            ser.bytesize = serial.EIGHTBITS
            ser.parity = serial.PARITY_NONE
            ser.stopbits = serial.STOPBITS_ONE
            print(f"Ponownie połączono z {serialPORT}")
            return ser
        except serial.SerialException as e:
            print(f"Nie można połączyć: {e}")


# --- Diagnostyka odbioru ------------------------------------------------------
# Liczniki ramek poprawnych i odrzuconych, zapisywane co DIAG_CO s do /data/diag.json
# (tmpfs, zero sieci). Pozwalaja sprawdzic, czy cos sie gubi.
# Odrzucone dzielimy wg dlugosci zadeklarowanej w naglowku ramki:
#   krotsza - ramka ucieta: zgubione bajty albo podzial na falszywym "16 68" w danych
#   dluzsza - dwie ramki sklejone (zgubiony bajt 16/68 na granicy)
#   crc     - dlugosc sie zgadza, ale CRC nie (przeklamany bajt)
DIAG_PLIK = "/data/diag.json"
DIAG_CO = 10
diag = {
    "start_uslugi": datetime.now().astimezone().isoformat(timespec="seconds"),
    "razem": {"poprawne": 0, "odrzucone_krotsza": 0, "odrzucone_dluzsza": 0, "odrzucone_crc": 0},
    "ostatnia_poprawna_ramka": None,
}
_diag_historia = []      # (monotonic, poprawne, odrzucone) do liczenia "na minute"
_diag_ostatni_zapis = 0.0


def diag_ramka(ramka, crc_ok):
    r = diag["razem"]
    if crc_ok:
        r["poprawne"] += 1
        diag["ostatnia_poprawna_ramka"] = datetime.now().astimezone().isoformat(timespec="seconds")
        return
    zadeklarowana = (ramka[1] | (ramka[2] << 8)) if len(ramka) >= 3 else None
    if zadeklarowana is None or len(ramka) < zadeklarowana:
        r["odrzucone_krotsza"] += 1
    elif len(ramka) > zadeklarowana:
        r["odrzucone_dluzsza"] += 1
    else:
        r["odrzucone_crc"] += 1


def diag_zapisz():
    global _diag_ostatni_zapis
    teraz = time.monotonic()
    if teraz - _diag_ostatni_zapis < DIAG_CO:
        return
    _diag_ostatni_zapis = teraz
    r = diag["razem"]
    odrz = r["odrzucone_krotsza"] + r["odrzucone_dluzsza"] + r["odrzucone_crc"]
    _diag_historia.append((teraz, r["poprawne"], odrz))
    while len(_diag_historia) > 1 and teraz - _diag_historia[0][0] > 60:
        _diag_historia.pop(0)
    t0, p0, o0 = _diag_historia[0]
    okres = teraz - t0
    diag["ostatnia_minuta"] = {
        "okres_s": round(okres),
        "poprawne": r["poprawne"] - p0,
        "odrzucone": odrz - o0,
    }
    diag["timestamp"] = datetime.now().astimezone().isoformat(timespec="seconds")
    tmp = DIAG_PLIK + ".tmp"
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(diag, f, ensure_ascii=False, indent=2)
        os.replace(tmp, DIAG_PLIK)
    except OSError as e:
        print(f"Błąd zapisu pliku {DIAG_PLIK}: {e}")


# systemctl stop/restart wysyla SIGTERM - zamien go na normalne wyjscie, zeby
# zadzialaly funkcje atexit (zapis oczekujacych polecen i pliku alarmu).
signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

source = open_source()

bajtCzytany = 0
bajtPoprzedni = 0
ramka = []

START_BYTE = 0
ROZMIAR_RAMKI_SHORT = 1
ADRES_ODBIORCY_BYTE = 3
ADRES_NADAWCY_BYTE = 4
TYP_NADAWCY_BYTE = 5
WERSJA_ECONET_BYTE = 6
TYP_RAMKI = 7
CRC_BYTE = -2
MESSAGE_START = 7


while True:
    try:
        if SOURCE == 'FILE':
            chunk = source.read(1)
            if len(chunk) == 0:
                break
        elif SOURCE == 'STREAM':
            chunk = source.recv(1)
        elif SOURCE == 'SERIAL':
            chunk = source.read(1)
    except serial.SerialException as e:
        print(f"Błąd odczytu z portu szeregowego: {e}")
        try:
            source.close()
        except Exception:
            pass
        source = reopen_serial()
        ramka = []
        bajtPoprzedni = 0
        continue
    except OSError as e:
        print(f"Błąd odczytu danych: {e}")
        time.sleep(1)
        continue

    try:
        bajtCzytany = ord(chunk)
    except TypeError:
        continue

    if bajtCzytany == RAMKA_START and bajtPoprzedni == RAMKA_STOP:

        if len(ramka) > 0:

            try:
                ramkaCRC = ramka[-2]
                print(ramka)
                myCRC = functools.reduce(lambda x, y: x ^ y, ramka[:-2])
                print(myCRC)
            except Exception:
                myCRC = ""
                ramkaCRC = "1"

            # Sam XOR nie wystarcza: dwie poprawne ramki sklejone (zgubiony bajt 0x16)
            # tez daja zgodny XOR. Dlatego sprawdzamy tez dlugosc z naglowka -
            # we wszystkich 1097 ramkach z logu zgadzala sie co do bajta.
            dlugosc_ok = len(ramka) >= 3 and (ramka[1] | (ramka[2] << 8)) == len(ramka)
            ramka_ok = (myCRC == ramkaCRC) and dlugosc_ok
            diag_ramka(ramka, ramka_ok)
            diag_zapisz()

            if ramka_ok:

                ramkaHEX = [f'{ramka[i]:02X}' for i in range(0, len(ramka))]
                message = ramka[MESSAGE_START:CRC_BYTE]
                messageHEX = ramkaHEX[MESSAGE_START:CRC_BYTE]

                if len(message) > 1:
                    print("")
                    print(f"== [ramka] [Typ: 0x{ramka[TYP_RAMKI]:02X}] [Długość:{len(ramka)}] [Nadawca: 0x{ramka[ADRES_NADAWCY_BYTE]:02X}] [Odbiorca: 0x{ramka[ADRES_ODBIORCY_BYTE]:02X}] [CRC:0x{ramkaCRC:02X}] ==")

                    rowsize = 12
                    for row in range(math.ceil(len(message) / rowsize)):
                        od = row * rowsize
                        do = od + rowsize if len(message) >= od + rowsize else len(message)
                        print(f"{od:03d}-{do-1:03d} \t{' '.join(messageHEX[od:do])}", end='')
                        print('   ' * ((od + rowsize) - do), end='')
                        print(f" \t{message[od:do]}")

                if len(ramka) > TYP_RAMKI and len(message) > 0:
                    if (ramka[ADRES_NADAWCY_BYTE], ramka[TYP_RAMKI]) not in ZNANE_RAMKI:
                        zapisz_nieznana(ramka, message)
                        try:
                            ecomax.zglos_inna_ramke(ramka[ADRES_NADAWCY_BYTE], ramka[ADRES_ODBIORCY_BYTE],
                                                    ramka[TYP_RAMKI], message, ramka_pelna=ramka)
                        except Exception as e:
                            print(f"Błąd zapisu ramki do alarmu: {e}")

                if len(ramka) > ADRES_NADAWCY_BYTE:
                    if ramka[ADRES_NADAWCY_BYTE] == NADAWCA_ECOSTER:
                        try:
                            ecoster.parseFrame(message)
                        except Exception as e:
                            print(f"Błąd parsowania ramki EcoSter: {e}")

                    if ramka[ADRES_NADAWCY_BYTE] == NADAWCA_ECOMAX:
                        try:
                            ecomax.parseFrame(message)
                        except Exception as e:
                            print(f"Błąd parsowania ramki EcoMax: {e}")

        ramka = []

    ramka.append(bajtCzytany)
    bajtPoprzedni = bajtCzytany
