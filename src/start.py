# Analizator EcoNet
# (C) 2020 Tomasz Król https://github.com/twkrol/econetanalyze
# Gwarancji żadnej nie daję. Ale można korzystać do woli i modyfikować wg potrzeb

import functools
import math
import socket
import struct
import sys
import time

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

            if myCRC == ramkaCRC:

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
