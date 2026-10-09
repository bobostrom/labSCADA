import struct

with open('/opt/scada/BaseDAT/cnl.dat', 'rb') as f:
    data = f.read()

# Let's inspect the last 200 bytes where RTAC channel was appended
print("Last 200 bytes:")
print(data[-200:])
