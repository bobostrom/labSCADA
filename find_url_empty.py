with open('/opt/scada/ScadaWeb/PlgWebPage.dll', 'rb') as f:
    d = f.read()

idx = 8301
print(d[idx-50:idx+250])
