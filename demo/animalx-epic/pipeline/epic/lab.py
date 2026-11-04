"""lab.py CLIENT DAY CAM VALUE tid... : add labels (VALUE 1, 0 or p)."""
import sys, json, pathlib
b = pathlib.Path(__file__).resolve().parent / 'source' / sys.argv[1] / sys.argv[2] / 'labels.json'
L = json.load(open(b)) if b.exists() else {}
v = sys.argv[4]; v = int(v) if v in '01' else v
for t in sys.argv[5:]:
    L.setdefault(sys.argv[3], {})[str(int(t))] = v
json.dump(L, open(b, 'w'), indent=0)
print({c: (sum(1 for x in d.values() if x == 1), len(d)) for c, d in L.items()})
