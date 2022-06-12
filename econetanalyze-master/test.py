import serial
serialPORT = "/dev/ttyUSB0"
serialBAUDRATE = 115200
ser = serial.Serial(serialPORT, serialBAUDRATE)
ser.bytesize = serial.EIGHTBITS
ser.parity = serial.PARITY_NONE
ser.stopbits = serial.STOPBITS_ONE
#ser.open()

ser.write("testing")
try:
    while 1:
        response = ser.readline()
        print (response)
except KeyboardInterrupt:
    ser.close()
