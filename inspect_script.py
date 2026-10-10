with open('/opt/scada/BaseDAT/script.dat', 'rb') as f:
    d = f.read()

print("script.dat size:", len(d))
# Look at fields of script.dat
print(d[:300])
