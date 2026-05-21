#ecoMAX 850 P2
import struct

print("Zaimportowano bibliotekę sterownika EcoMax850P2")
filename = "/data/odczyty.txt"

def parseFrame(message):
    if message[0] == 0x08:
        parseFrame08(message)
    else:
        print(f"Parser EcoMax: Nieznany typ ramki 0x{message[0]:02X}")

def parseFrame08(message):
    OPERATING_STATUS_byte = 27
    TEMP_CWU_float = 76
    TEMP_TORCH_float = 84
    TEMP_CO_float = 80
    TEMP_WEATHER_float = 92
    TEMP_MIXER_float = 88
    TEMP_MIXER_SET_byte = 156
    MIXER_SET_percent_byte = 222
    FUEL_STREAM_float = 250
    TEMP_CWU_SET_byte = 153
    TEMP_CO_SET_byte = 154
    FLAME_bytes = 36
    BOILER_POWER_float = 246
    POWER100_TIME_short = 255
    POWER50_TIME_short = 257
    POWER30_TIME_short = 259
    FEEDER_TIME_short = 261
    IGNITIONS_short = 263
    AIRFLOW_percent_byte = 245

    OPERATION_STATUSES = {0:'WYŁĄCZONY', 1:'ROZPALANIE', 2:'PRACA', 4:'WYGASZANIE', 5:'POSTÓJ', 6:'PRACA RĘCZNA', 7:'ALARM', 8:'CZYSZCZENIE'}
    print("")

    try:
        OP = OPERATION_STATUSES[message[OPERATING_STATUS_byte]] if message[OPERATING_STATUS_byte] in OPERATION_STATUSES else str(message[OPERATING_STATUS_byte])
        tempCWU = struct.unpack("f", bytes(message[TEMP_CWU_float:TEMP_CWU_float+4]))[0]
        print(f"Temperatura CWU: {tempCWU:.1f}")
        tempCO = struct.unpack("f", bytes(message[TEMP_CO_float:TEMP_CO_float+4]))[0]
        print(f"Temperatura CO: {tempCO:.1f}")
        TEMP_CO_SET_byte_val = message[TEMP_CO_SET_byte]
        print(f"Temperatura SET CO: {TEMP_CO_SET_byte_val}")
        TEMP_CWU_SET_byte_val = message[TEMP_CWU_SET_byte]
        print(f"Temperatura SET CWU: {TEMP_CWU_SET_byte_val}")
        tempPogodowa = struct.unpack("f", bytes(message[TEMP_WEATHER_float:TEMP_WEATHER_float+4]))[0]
        print(f"Temperatura pogodowa: {tempPogodowa:.1f}")
        fuelStream = struct.unpack("f", bytes(message[FUEL_STREAM_float:FUEL_STREAM_float+4]))[0]
        print(f"Strumien paliwa: {fuelStream:.1f}")
        tempPodajnika = struct.unpack("f", bytes(message[TEMP_TORCH_float:TEMP_TORCH_float+4]))[0]
        print(f"Temperatura palnika: {tempPodajnika:.1f}")
        tempMieszacza = struct.unpack("f", bytes(message[TEMP_MIXER_float:TEMP_MIXER_float+4]))[0]
        print(f"Temperatura mieszacza: {tempMieszacza:.1f}")
        TEMP_MIXER_SET_byte_val = message[TEMP_MIXER_SET_byte]
        print(f"Temperatura ust mieszacza: {TEMP_MIXER_SET_byte_val}")
        AIRFLOW_percent_byte_val = message[AIRFLOW_percent_byte]
        print(f"Nadmuch: {AIRFLOW_percent_byte_val} %")
        MIXER_SET_percent_byte_val = message[MIXER_SET_percent_byte]
        print(f"Ustawienie mieszacza procent: {MIXER_SET_percent_byte_val} %")
        BOILER_POWER_float_val = struct.unpack("f", bytes(message[BOILER_POWER_float:BOILER_POWER_float+4]))[0]
        print(f"Moc kotła: {BOILER_POWER_float_val:.1f}")
        flame = message[FLAME_bytes]
        print(f"flame: {flame:d}%")
        print("ustawienia serwisowe")
        POWER100_TIME_short_val = struct.unpack("h", bytes(message[POWER100_TIME_short:POWER100_TIME_short+2]))[0]
        print(f"Praca MAX: {POWER100_TIME_short_val}h")
        POWER50_TIME_short_val = struct.unpack("h", bytes(message[POWER50_TIME_short:POWER50_TIME_short+2]))[0]
        print(f"Praca ŚRED: {POWER50_TIME_short_val}h")
        POWER30_TIME_short_val = struct.unpack("h", bytes(message[POWER30_TIME_short:POWER30_TIME_short+2]))[0]
        print(f"Praca MIN: {POWER30_TIME_short_val}h")
        IGNITIONS_short_val = struct.unpack("h", bytes(message[IGNITIONS_short:IGNITIONS_short+2]))[0]
        print(f"Rozpalen: {IGNITIONS_short_val}")
        FEEDER_TIME_short_val = struct.unpack("h", bytes(message[FEEDER_TIME_short:FEEDER_TIME_short+2]))[0]
        print(f"Praca podajnika: {FEEDER_TIME_short_val}h")
        print(" ")
    except (IndexError, struct.error) as e:
        print(f"Błąd parsowania ramki EcoMax08 (zbyt krótka ramka lub błędne dane): {e}")
        return
    except Exception as e:
        print(f"Nieoczekiwany błąd parsowania EcoMax08: {e}")
        return

    results = "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s" % (
        tempCWU, tempCO, tempPogodowa, tempPodajnika, tempMieszacza,
        OP, TEMP_CO_SET_byte_val, TEMP_CWU_SET_byte_val,
        TEMP_MIXER_SET_byte_val, AIRFLOW_percent_byte_val,
        MIXER_SET_percent_byte_val, fuelStream, BOILER_POWER_float_val
    )
    try:
        with open(filename, 'w') as outfile:
            outfile.write(results)
    except OSError as e:
        print(f"Błąd zapisu pliku {filename}: {e}")

    try:
        with open("/data/message.txt", 'w') as file_message:
            file_message.write("%s" % (message,))
    except OSError as e:
        print(f"Błąd zapisu pliku /data/message.txt: {e}")
