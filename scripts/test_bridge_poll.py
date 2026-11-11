import serial, struct, time

ser = serial.Serial('/dev/ttyACM0', 115200, timeout=1)
# Modbus RTU read holding registers: Unit ID 1, Function 3, Start 0, Count 8
# CRC16 for [0x01, 0x03, 0x00, 0x00, 0x00, 0x08] is 0x44, 0x0C
req = bytes([0x01, 0x03, 0x00, 0x00, 0x00, 0x08, 0x44, 0x0C])
ser.write(req)
time.sleep(0.15)
resp = ser.read(100)
print('Response bytes:', len(resp), resp.hex())
if len(resp) >= 21 and resp[0] == 1 and resp[1] == 3:
    regs = struct.unpack('>8h', resp[3:19])
    print('Decoded Registers:', regs)
    temp = regs[0] / 10.0
    batt = regs[1]
    fault = regs[2]
    rssi = regs[3]
    age = regs[6]
    flags = regs[7]
    print(f'Slot 1: Temp={temp} C, Batt={batt} mV, Fault={fault}, RSSI={rssi} dBm, Age={age}s, Flags=0x{flags:04X}')
ser.close()

