# Analizator EcoNet
# (C) 2020 Tomasz Król https://github.com/twkrol/econetanalyze
# Gwarancji żadnej nie daję. Ale można korzystać do woli i modyfikować wg potrzeb

import json
import os
import struct
from datetime import datetime

# Panel rozsyla co ok. 0,85 s ramke 0x89 z napisem "TIME" i swoim zegarem:
# [0x89, 'T','I','M','E', godz, min, sek, rok L, rok H, miesiac, dzien, dzien_tyg, ?, ?, ...]
# Zapisujemy ja do /data/panel.json (tmpfs) razem z odchylka wzgledem zegara Pi.
PANEL_PLIK = "/data/panel.json"

print("Zaimportowano bibliotekę sterownika EcoSter/EcoTouch")

def parseFrame(message):
    if message[0] == 0x89:
        parseFrame89(message)
    else:
        print(f"Parser EcoSter: Nieznany typ ramki 0x{message[0]:02X}")

def parseFrame89(message):
    TEMP_HOME_SET_FLOAT = 17
    TEMP_HOME_CURR_FLOAT = 21
    HOURS_byte = 5
    MINUTE_byte = 6
    SECOUND_byte = 7
    YEAR_short = 8
    MOUNT_byte = 10
    DAY_byte = 11
    print("")

    try:
        HOURS_byte_val = message[HOURS_byte]
        print(f"Godzina: {HOURS_byte_val}")
        MINUTE_byte_val = message[MINUTE_byte]
        print(f"Minuta: {MINUTE_byte_val}")
        SECOUND_byte_val = message[SECOUND_byte]
        print(f"Sekunda: {SECOUND_byte_val}")
        YEAR_short_val = struct.unpack("h", bytes(message[YEAR_short:YEAR_short+2]))[0]
        print(f"Rok: {YEAR_short_val}")
        MOUNT_byte_val = message[MOUNT_byte]
        print(f"Miesiac: {MOUNT_byte_val}")
        DAY_byte_val = message[DAY_byte]
        print(f"Dzien: {DAY_byte_val}")
        zapisz_zegar(message)
    except (IndexError, struct.error) as e:
        print(f"Błąd parsowania ramki EcoSter89 (zbyt krótka ramka lub błędne dane): {e}")
    except Exception as e:
        print(f"Nieoczekiwany błąd parsowania EcoSter89: {e}")


def zapisz_zegar(message):
    """Zegar panelu + odchylka [s] wzgledem zegara Pi (synchronizowanego z internetem)."""
    if len(message) < 13 or bytes(message[1:5]) != b"TIME":
        return
    try:
        zegar = datetime(message[8] | (message[9] << 8), message[10], message[11],
                         message[5], message[6], message[7])
    except ValueError:
        return                                   # bzdurna data - nie zapisuj
    teraz = datetime.now().replace(microsecond=0)
    dane = {
        # panel nie podaje strefy - zakladamy czas lokalny (jak na wyswietlaczu)
        "zegar_panelu": zegar.astimezone().isoformat(timespec="seconds"),
        "dzien_tygodnia": message[12],           # 1 = poniedzialek ... 7 = niedziela
        "odchylka_s": round((zegar - teraz).total_seconds()),
        "odczyt": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    try:
        tmp = PANEL_PLIK + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dane, f, ensure_ascii=False)
        os.replace(tmp, PANEL_PLIK)
    except OSError as e:
        print(f"Błąd zapisu pliku {PANEL_PLIK}: {e}")
