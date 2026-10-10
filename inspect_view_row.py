with open('/opt/scada/BaseDAT/view.dat', 'rb') as f:
    d = f.read()

idx = d.find(b'IVF Clinic Dashboard')
print("Match at", idx)
print(d[idx-100:idx+60])
