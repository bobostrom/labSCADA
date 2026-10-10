with open('/opt/scada/ScadaServer/ScadaServerEngine.dll', 'rb') as f:
    d = f.read()

import re
for m in re.finditer(b'Added the following dependencies', d):
    print("Match at", m.start())
    print(d[max(0, m.start()-100):min(len(d), m.start()+200)])
