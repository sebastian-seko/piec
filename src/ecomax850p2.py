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
    FLAME_float = 72
    BOILER_POWER_float = 246
    POWER100_TIME_short = 255
    POWER50_TIME_short = 257
    POWER30_TIME_short = 259
    FEEDER_TIME_short = 261
    IGNITIONS_short = 263
    AIRFLOW_percent_byte = 245
    OUTPUTS_byte = 28   # bitowa mapa stanow wyjsc (bit7..bit0)

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
        flame = struct.unpack("f", bytes(message[FLAME_float:FLAME_float+4]))[0]
        print(f"flame: {flame:.1f}%")
        # Stany wyjsc - jeden bajt, bity 7..0
        outputs = message[OUTPUTS_byte]
        fan               = "ON" if (outputs >> 0) & 1 else "OFF"
        feeder            = "ON" if (outputs >> 1) & 1 else "OFF"
        feeder2           = "ON" if (outputs >> 2) & 1 else "OFF"
        cleaning_actuator = "ON" if (outputs >> 3) & 1 else "OFF"
        ignition          = "ON" if (outputs >> 4) & 1 else "OFF"
        boiler_pump       = "ON" if (outputs >> 5) & 1 else "OFF"
        cwu_pump          = "ON" if (outputs >> 6) & 1 else "OFF"
        mixer_pump        = "ON" if (outputs >> 7) & 1 else "OFF"
        print(f"Wyjścia [{outputs:08b}]: went={fan} podajnik={feeder} podajnik2={feeder2} "
              f"czyszczak={cleaning_actuator} zapalarka={ignition} "
              f"p.piec={boiler_pump} p.cwu={cwu_pump} p.miesz={mixer_pump}")
        print("ustawienia serwisowe")
        # Blok serwisowy = 5 licznikow (short LE, kolejno: praca 100%, 50%, 30%,
        # podajnik, rozpalenia). Jego pozycja potrafi przesunac sie nawet o
        # kilkanascie bajtow wzgledem POWER100_TIME_short (zmiennej dlugosci
        # sekcje czujnikow/alarmow przed nim). Ramka jest na koncu wypelniona
        # zerami, a blok to OSTATNI zwarty ciag niezerowych bajtow - namierzamy
        # go skanujac od konca. Gdy nie znaleziono sensownego ciagu (>=10 B) -
        # fallback do statycznego offsetu.
        svc_end = len(message) - 1
        while svc_end > 0 and message[svc_end] == 0:
            svc_end -= 1
        svc_base = svc_end
        while svc_base > 0 and message[svc_base - 1] != 0:
            svc_base -= 1
        if svc_end - svc_base + 1 < 10:
            svc_base = POWER100_TIME_short  # fallback: statyczne offsety
        POWER100_TIME_short_val = struct.unpack("h", bytes(message[svc_base:svc_base+2]))[0]
        POWER50_TIME_short_val  = struct.unpack("h", bytes(message[svc_base+2:svc_base+4]))[0]
        POWER30_TIME_short_val  = struct.unpack("h", bytes(message[svc_base+4:svc_base+6]))[0]
        FEEDER_TIME_short_val   = struct.unpack("h", bytes(message[svc_base+6:svc_base+8]))[0]
        IGNITIONS_short_val     = struct.unpack("h", bytes(message[svc_base+8:svc_base+10]))[0]
        print(f"Blok serwisowy @ bajt {svc_base}")
        print(f"Praca MAX: {POWER100_TIME_short_val}h")
        print(f"Praca ŚRED: {POWER50_TIME_short_val}h")
        print(f"Praca MIN: {POWER30_TIME_short_val}h")
        print(f"Rozpalen: {IGNITIONS_short_val}")
        print(f"Praca podajnika: {FEEDER_TIME_short_val}h")
        print(" ")
    except (IndexError, struct.error) as e:
        print(f"Błąd parsowania ramki EcoMax08 (zbyt krótka ramka lub błędne dane): {e}")
        return
    except Exception as e:
        print(f"Nieoczekiwany błąd parsowania EcoMax08: {e}")
        return

    results = "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s" % (
        tempCWU, tempCO, tempPogodowa, tempPodajnika, tempMieszacza,
        OP, TEMP_CO_SET_byte_val, TEMP_CWU_SET_byte_val,
        TEMP_MIXER_SET_byte_val, AIRFLOW_percent_byte_val,
        MIXER_SET_percent_byte_val, fuelStream, BOILER_POWER_float_val, flame,
        POWER100_TIME_short_val, POWER50_TIME_short_val, POWER30_TIME_short_val,
        IGNITIONS_short_val, FEEDER_TIME_short_val,
        mixer_pump, cwu_pump, boiler_pump, ignition,
        cleaning_actuator, feeder2, feeder, fan
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
