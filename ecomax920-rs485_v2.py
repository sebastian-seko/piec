###
# Autor: miszko / miszko@tempra.org / sierpien 2019r.#
# Skrypt w python sluzacy odczytaniu danych wysylanych przez port G2 w sterowniku Plum ecoMAX920 przebrandowanym na Kostrzewa.
# Wystarczy podpiac sie swoim portem RS485 w D+ i D- portu G2 w sterowniku (wtyczka rj11). Ja uzylem konwertera RS485->USB opartego o popularny chip ftdi ft232r,
# w systemie widocznym u mnie jako /dev/ttyUSB0. Popularnosc chipu sprawia, ze nie ma problemow ze sterownikiem. U mnie dziala to na routerze TP-Link TL-WDR3600 v1
# na ktory wgralem LEDE 18.06 (OpenWRT). Idealny sprzet do pracy w kotlowni ;)
#
# Na ten moment odczytane sa: temp. kotla (zasilania), powrotu, palnika oraz procent plomienia. Brakuje odczytu z innych czujnikow (np. CWU, zewnetrzny) oraz mocy kotla.
#
# Brak tu jakiejkolwiek funkcji sprawdzajacej, program po prostu liczy bajty od puntu zaczepienia i wyciaga dane. Odczyty moga byc obarczone bledem!
# Jest maly proof-of-conept czyli dzialajaca demonstracja jak mozna toodczytac. Wiele usprawnien mozna tutaj zrobic, kod nie byl pisany prze profesjonaliste.
#
# Szczegolne podziekowania dla przemo_ns@elektroda (https://www.elektroda.pl/rtvforum/uzytkownik3313912.html) w zlokalizowaniu danych w bloku.
# Link do tematu: https://www.elektroda.pl/rtvforum/viewtopic.php?t=3346727
# 
#
# werjsa 2
# autor Coorass
#-automatyczne wykrywanie ramek na podstawie standardu MBUS (https://github.com/ganehag/pyMeterBus) 
#-wyliczanie sum kontrolnych oraz weryfikacja
#-pruby automatycznego dekodowania wartosci 

###

import serial
import struct, binascii
import sys

# dodawanie na poczatku 0 (ZERO) do HEXa, gdyz hex() zwraca taki, czyli np. 0xb, a chcemy 0x0b
def add0tohex(hex):
   num_hex_chars = len(hex)
   if num_hex_chars == 3:
      hex = ''.join(('0x0',hex[2:3]))
      return hex
   else:
     return hex



def revert(hex):
  hexreverse=''
  arr=hex.split(' ')
  for i in xrange(len(arr)):
    hexreverse = hexreverse + arr[ -i - 1 ]
  return hexreverse

def revertstring(hex):
  hexreverse=''
  arr=map(''.join, zip(*[iter(hex)]*2))
  for i in xrange(len(arr)):
    hexreverse = hexreverse + arr[ -i - 1 ]
  return hexreverse

def b4float(hexinput):

  hexinput = str.join('', ("0x",hexinput[-2:]+hexinput[-4:-2]+hexinput[-6:-4]+hexinput[-8:-6]))
  if int(hexinput,16) <= sys.maxint:
    hexinput = struct.unpack('f',struct.pack('i',int(hexinput,16)))
    # hexinput = struct.unpack('f',struct.pack("<i", (hexinput).encode('hex')))
    return round(hexinput[0],2)
    print(hexinput + " => " + str(round(hexinput[0],2)))
  else:
    # hexinput = struct.unpack('f',struct.pack("<i", (int(hexinput,16) + 2**32) % 2**32).encode('hex'))
    val = int(hexinput,16) - sys.maxint
    hexinput = struct.unpack('f',struct.pack('i',val))

    # struct.pack("<I", -2 + 2**32).encode('hex')
    return str('-' + str(round(hexinput[0],2)))
        # val = Int32.Parse(hexinput, System.Globalization.NumberStyles.AllowHexSpecifier)
    # val = val - 0xFFFFFF - 1
    # return 0 

def b2float(hexinput):
  hexinput = str.join('', ("0x",hexinput[-2:]+hexinput[-4:-2]))
  if int(hexinput,16) <= sys.maxint:
    hexinput = struct.unpack('f',struct.pack('i',int(hexinput,16)))
    return round(hexinput[0],2)
    print(hexinput + " => " + str(round(hexinput[0],2)))
  else:
    return 0



try:
  ser = serial.Serial( # parametry polaczenia
    port="/dev/ttyUSB0",
    baudrate=115200,
    bytesize=8,
    parity=serial.PARITY_NONE,
    stopbits=1,
    timeout=1,
    xonxoff=False,
    rtscts=True,
    dsrdtr=False
  )
  ser.isOpen() # otwieramy port
  print ("Port zostal otwarty") # port otwarty

except IOError: # jezeli byl otwarty, sprobujmy go zamknac i otworzyc
  ser.close()
  ser.open()
  print ("Port zostal zamkniety i otwarty")

bajtCzytany = '' # bajt aktualnie przetwarzany


#pomocnicze
startCzytaniaRamki = 0
licznikBajtow = 0
ramka = ''
CRC=0
frame = ''
counter = 0 
wykaznumeryzny = 0
poprzedniHEX = ''
ramkakompletna = 0
programStart = 1
licznikbitow = 0
ramkaStart = 0

while True:
  bajtCzytany = hex(ord(ser.read()))
  czystyHex=add0tohex(bajtCzytany)[2:4]
  # print(str(czystyHex))

  if czystyHex == str(68) and poprzedniHEX == str(16):
    programStart = 0
    ramkaStart = 1
    licznikbitow = 0 

  if licznikbitow == 0 and  programStart == 0:
    ramkakompletna = 1

  
    if ramkakompletna == 1: #zaczynamy analize ramki

      startCzytaniaRamki = 0
      ramkakompletna = 0

      print("====================")
      print("ramka: " + ramka)
      ramkaCRC = ramka[-4:-2]
      print("ramkaCRC: " + ramkaCRC)
      ramkaDATA = ramka[:-4]
      print("ramkaDATA: " + ramkaDATA)
      t = [(ramkaDATA[i:i+2]) for i in range(0, len(ramkaDATA), 2)] 
      # print(counter)
      counter = 0 
      
      for b in t:
        if counter == 0:
          A = int(b,16)
        if counter == 1:
          B = int(b,16)
          CRC = (A ^ B)
          # print(str(A) +' ' + str(B) +' ' + str(CRC))
        if counter > 1:
          A = CRC
          B = int(b,16)
          CRC = (A ^ B)
          # print(str(A) +' ' + str(B) +' ' + str(CRC))
        counter = counter + 1 

      print("wyliczone CRC: " + str(hex(CRC)))



#weryfikacja CRC
      if hex(CRC)[2:4] == ramkaCRC:
      # if ramkaCRC == ramkaCRC:
        print("ramka poprawna, dekoduje")
        ramkaLen=int(ramkaDATA[4:6]+ramkaDATA[2:4],16)
        print("dlugosc ramki: "+str(ramkaLen))
        if (ramkaLen ==10):
          dane=ramkaDATA[-2:]+ramkaDATA[-4:-2]+ramkaDATA[-6:-4]+ramkaDATA[-8:-6]
          print(dane)
          dane = str.join('', ("0x", dane))
          dane = struct.unpack('f',struct.pack('i',int(dane,16)))
          print("dane: "+str(round(dane[0],2)))
        
        if ramkaLen > 100:
          wykaznumeryzny = 0
          # print(ramkaDATA[171:180])
          ramkaDATA=ramkaDATA[:-6]
          #przepisujemy ramke 2bitowo od tylu aby latwiej bylo czytac dane
          i=len(ramkaDATA)
          while i > 8 :
            wykaznumeryzny = wykaznumeryzny + 1
            
            tableData=[['x'+str(wykaznumeryzny),
            ramkaDATA[i-8:i],
            str(b4float(ramkaDATA[i-8:i])),
            '2bfloat: '+str(b2float(ramkaDATA[i-8:i-4])),
            ' : ',
            str(b2float(ramkaDATA[i-4:i])),
            'int2b:',
            str(int( revertstring(ramkaDATA[i-8:i-4]),16)),
            ':',
            str(int( revertstring(ramkaDATA[i-4:i]),16)),
            
            'int:',
            str(int(ramkaDATA[i-8:i-6],16)),
            ':',
            str(int(ramkaDATA[i-6:i-4],16)),
            ':',
            str(int(ramkaDATA[i-4:i-2],16)),
            ':',
            str(int(ramkaDATA[i-2:i],16))
            ]]
            for row in tableData:
              print("{: >3} {: >9} {: >20} {: >15} {: >2} {: >8} {: >10} {: >6} {: >2}  {: >5} {: >10} {: >4} {: >2} {: >4} {: >2} {: >4} {: >2} {: >4} ".format(*row))
            # print('num'+str(wykaznumeryzny) + ":" + ramkaDATA[i-8:i] + " => "+ str(b4float(ramkaDATA[i-8:i])) + '\t\t2bfloat:' + str(b2float(ramkaDATA[i-8:i-4])) + ' || ' + str(b2float(ramkaDATA[i-4:i])) + '\t\t int2b:' + str(int( revertstring(ramkaDATA[i-8:i-4]),16)) + ' || ' + str(int( revertstring(ramkaDATA[i-4:i]),16))  + '\t\t int:' + str(int(ramkaDATA[i-8:i-6],16))+ ' || ' + str(int(ramkaDATA[i-6:i-4],16))+' || ' + str(int(ramkaDATA[i-4:i-2],16)) +' || ' + str(int(ramkaDATA[i-2:i],16))        )
            # dane = ramkaDATA[i-8:i]
            # dane = str.join('', ("0x",dane[-2:]+dane[-4:-2]+dane[-6:-4]+dane[-8:-6]))
            # # print(dane)
            # if int(dane,16) <= sys.maxint:
            #   dane = struct.unpack('f',struct.pack('i',int(dane,16)))
            #   print(ramkaDATA[i-8:i] + " => " + str(round(dane[0],2))) 
            # else:
            #   print(ramkaDATA[i-8:i])
   
            ramkaDATA=ramkaDATA[:i-8]
            i = len(ramkaDATA)
          #zdekodowane parametry 4bajty float
          print("temp pieca \t" + str(b4float(ramka[171:180])))
          print("temp podajnika \t" + str(b4float(ramka[180:188])))
          print("temp CWU \t" + str(b4float(ramka[188:196])))
          print("temp Powrotu\t" + str(b4float(ramka[196:204])))
          print("temp miesz 1\t" + str(b4float(ramka[204:212])))
          print("temp miesz 2\t" + str(b4float(ramka[212:220])))
          print("??????\t" + str(b4float(ramka[220:228]))) ##niewiadomo
          print("?????\t" + str(b4float(ramka[228:236]))) ##niewiadomo
          print("temp zewnetrz\t" + str(b4float(ramka[236:244])))
          print("temp spalin\t" + str(b4float(ramka[244:252])))
          #nastepne 12 sa NAN
          print("temp minimalna kotla \t" + str(  int( revertstring(ramka[348:352]),16))) 
          print("temp zadana CWU \t" + str(  int( revertstring(ramka[352:356]),16)))
          print("temperatura zadana mieszacza 1\t" + str(int(ramka[356:358],16)))
          print("temperatura minimalna mieszacza 2\t" + str(int(ramka[358:360],16)))

          print("Czas pracy na mocy 100%\t" + str(int(revertstring(ramka[540:544]),16)))
          print("Czas pracy na mocy 50%\t" + str(int(revertstring(ramka[544:548]),16)))
          print("Czas pracy na mocy 30%\t" + str(int(revertstring(ramka[548:552]),16))) 
          print("Czas pracy podajnika\t" + str(int(revertstring(ramka[552:556]),16)))
          print("Ilosc rozpalen\t" + str(int(revertstring(ramka[556:560]),16)))


          print("~")

          

      print('')
      CRC=0
      ramka = ''

  if ramkaStart == 1:
    ramka = str(ramka) + str(czystyHex)
    licznikbitow = licznikbitow + 1
  
  poprzedniHEX = czystyHex
