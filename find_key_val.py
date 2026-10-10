with open('/opt/scada/ScadaComm/ScadaCommon.dll', 'rb') as f:
    d = f.read()

import re
for m in re.finditer(b'SecretKey', d):
    # print the enclosing namespace or class or method if possible
    print(d[max(0, m.start()-40):min(len(d), m.start()+40)])
