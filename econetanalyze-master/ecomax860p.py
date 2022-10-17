# Analizator EcoNet
# (C) 2020 Tomasz Król https://github.com/twkrol/econetanalyze
# Gwarancji żadnej nie daję. Ale można korzystać do woli i modyfikować wg potrzeb

import struct

print("Zaimportowano bibliotekę sterownika EcoMax860P")
filename = "/data/odczyty.txt"
#outfile = open(filename, 'w')

# funkcja kierująca odpowiedni typ ramki do obsługującej ją funkcji parsującej
def parseFrame(message):
    if message[0] == 0x08:
        parseFrame08(message)
    else:
        print(f"Parser EcoMax: Nieznany typ ramki 0x{message[0]:02X}")

# funkcja parsująca ramkę typu 0x08 sterownika EcoMax860P
def parseFrame08(message):
    #mapa komunikatu stanu ze sterownika pieco EcoMax860P Lazar SmartFire
    # typ ramki = 0x08          #[0]
    OPERATING_STATUS_byte = 27  #[33] seko
    TEMP_CWU_float = 76         #[74-77] seko
    TEMP_FEEDER_float = 84      #[78-81] sekoi
    TEMP_CO_float = 80          #[82-85] seko
    #TEMP_BURNER_float = 84
    TEMP_WEATHER_float = 92     #[90-93] seko
    TEMP_EXHAUST_float = 94     #[94-97]
    TEMP_MIXER_float = 88      #[106-109] seko
    TEMP_MIXER_SET_byte = 156      #[106-109] seko
    FUEL_STREAM_float = 249
    #pompa-stany 4B
    #pompa-nastawy 4B
    #numT 1B
    #iloczyn numT * 5
    TEMP_CWU_SET_byte = 153    #[146] lub #29 seko
    TEMP_CO_SET_byte = 154      #[148] seko
    #statusCO 1B
    #statusCWU 1B
    #alarmsNo 1B  #[187]
    #iloczyn alarmsNo * 1B
    FUEL_LEVEL_byte=189         #[189]
    FLAME_bytes = 36            #seko
    #transmission_BYTE=190
    #fanPower_FLOAT=191-194
    BOILER_POWER_byte=196       #[196]
    #boilerPowerKW_FLOAT=197-200
    #fuelStream=201-204
    #thermostat=205
    #versionInfo=204-208
    #moduleBSoftVer=209-211
    #moduleCSoftVer=212-214
    #moduleLambdaSoftVer=215-217 ?a nie zawór mieszacza?
    #moduleEcoSTERSoftVer=218-220
    #modulePanelSoftVer=221-223
    #lambdaStatus=224
    #lambdaSet=225
    LAMBDA_LEVEL_float=226      #[226-229]
    #OXYGEN_float = 230          #[230-233]
    POWER100_TIME_short = 255   #[235-236] seko
    POWER50_TIME_short = 257    #[237-238] seko
    POWER30_TIME_short = 259    #[239-240] seko
    FEEDER_TIME_short = 261     #[241-242] seko
    IGNITIONS_short = 263       #[243-244] seko
    AIRFLOW_percent_byte = 245          #seko

    #OPERATION_STATUSES = {0:'WYŁĄCZONY', 1:'ROZPALANIE', 2:'STABILIZACJA', 3:'PRACA', 4:'NADZÓR', 5:'WYGASZANIE', 6:'POSTÓJ', 7:'WYGASZANIE NA ŻĄDANIE', 9:'ALARM', 10:'ROZSZCZELNIENIE'}
    OPERATION_STATUSES = {0:'WYŁĄCZONY', 1:'ROZPALANIE', 2:'PRACA', 4:'WYGASZANIE', 5:'POSTÓJ' , 7:'ALARM', 8:'CZYSZCZENIE'}
    print("")

    #Stan pieca [33]
    #print(f"Stan pieca: {OPERATION_STATUSES[message[OPERATING_STATUS_byte]] if message[OPERATING_STATUS_byte] in OPERATION_STATUSES else str(message[OPERATING_STATUS_byte]) }")
    #print(f"Poziom paliwa: {message[OPERATING_STATUS_byte]}%")
    OP = OPERATION_STATUSES[message[OPERATING_STATUS_byte]] if message[OPERATING_STATUS_byte] in OPERATION_STATUSES else str(message[OPERATING_STATUS_byte])
    #OP = message[OPERATING_STATUS_byte]
    #Poziom paliwa [189]
    #print(f"Poziom paliwa: {message[FUEL_LEVEL_byte]}%")

    #Temperatura CWU [74-77]
    tempCWU = struct.unpack("f", bytes(message[TEMP_CWU_float:TEMP_CWU_float+4]))[0]
    print(f"Temperatura CWU: {tempCWU:.1f}")

    #Temperatura CO [82-85]
    tempCO = struct.unpack("f", bytes(message[TEMP_CO_float:TEMP_CO_float+4]))[0]
    print(f"Temperatura CO: {tempCO:.1f}")

    TEMP_CO_SET_byte_val = message[TEMP_CO_SET_byte]
    print(f"Temperatura SET CO: {TEMP_CO_SET_byte_val}")
    TEMP_CWU_SET_byte_val = message[TEMP_CWU_SET_byte]
    print(f"Temperatura SET CWU: {TEMP_CWU_SET_byte_val}")
    #Temperatura pogodowa
    tempPogodowa= struct.unpack("f", bytes(message[TEMP_WEATHER_float:TEMP_WEATHER_float+4]))[0]
    print(f"Temperatura pogodowa: {tempPogodowa:.1f}")

    #Temperatura spalin
    #tempSpalin = struct.unpack("f", bytes(message[TEMP_EXHAUST_float:TEMP_EXHAUST_float+4]))[0]
    #print(f"Temperatura spalin: {tempSpalin:.1f}")

    #strumien paliwa
    fuelStream= struct.unpack("f", bytes(message[FUEL_STREAM_float:FUEL_STREAM_float+4]))[0]
    print(f"Strumien paliwa: {fuelStream:.1f}")

    #Temperatura podajnika
    tempPodajnika = struct.unpack("f", bytes(message[TEMP_FEEDER_float:TEMP_FEEDER_float+4]))[0]
    print(f"Temperatura palnika: {tempPodajnika:.1f}")

    #Tlen
    #tlen = struct.unpack("f", bytes(message[OXYGEN_float:OXYGEN_float+4]))[0]
    #print(f"Tlen: {tlen:.1f}%")

    #Temperatura mieszacza
    tempMieszacza = struct.unpack("f", bytes(message[TEMP_MIXER_float:TEMP_MIXER_float+4]))[0]
    print(f"Temperatura mieszacza: {tempMieszacza:.1f}")
    #Temperatura ust mieszacza
    TEMP_MIXER_SET_byte_val = message[TEMP_MIXER_SET_byte]
    print(f"Temperatura ust mieszacza: {TEMP_MIXER_SET_byte_val}")
    AIRFLOW_percent_byte_val = (message[AIRFLOW_percent_byte])
    print(f"Nadmuch: {AIRFLOW_percent_byte_val} %")
    #Moc kotła
    #moc = message[BOILER_POWER_byte]
    #print(f"Moc kotła: {moc:d}%")    
    #ogien 
    flame_val = message[FLAME_bytes] # nie działa prawidłowo
    print(f"flame: {flame_val} %")

    print ("ustawienia serwisowe")
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
    #LambdaSet
    #lambdaLevel = struct.unpack("f", bytes(message[226:226+4]))[0]
    #print(f"Lambda: {lambdaLevel:.1f}")

    #Zawór mieszacza?
    #m = message[215]
    #print(f"Zawór mieszacza?: {m:d}%")
    print (" ")
    outfile = open(filename, 'w')
    results = "%s, %s, %s, %s, %s, %s, %s, %s, %s" % (tempCWU,tempCO,tempPogodowa,tempPodajnika,tempMieszacza,OP,TEMP_CO_SET_byte_val,TEMP_CWU_SET_byte_val,TEMP_MIXER_SET_byte_val)
    outfile.write(results)
    outfile.close()
