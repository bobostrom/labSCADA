with open('/opt/scada/BaseDAT/cnl.dat', 'rb') as f:
    d = f.read()

import re
m = re.search(b'IncubatorAlarm_01', d)
if m:
    idx = m.start()
    # Let's search back for the channel number or print preceding 80 bytes
    print("Match at", idx)
    print(d[idx-80:idx+40])
