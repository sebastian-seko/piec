# Analizator EcoNet
# (C) 2020 Tomasz Król https://github.com/twkrol/econetanalyze
# Gwarancji żadnej nie daję. Ale można korzystać do woli i modyfikować wg potrzeb

import struct

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
    except (IndexError, struct.error) as e:
        print(f"Błąd parsowania ramki EcoSter89 (zbyt krótka ramka lub błędne dane): {e}")
    except Exception as e:
        print(f"Nieoczekiwany błąd parsowania EcoSter89: {e}")
