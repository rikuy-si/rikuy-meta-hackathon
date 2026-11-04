"""Phase J report: hole minutes (> 60 s, inside first..last seen) before and after the rescue, per client/day."""
import json, pathlib
ROOT = pathlib.Path(__file__).resolve().parent
sod = lambda s: sum(int(v) * m for v, m in zip(s.split(':'), (3600, 60, 1)))

def holes(pres, A, Z):
    iv = sorted((i['w0'], i['w1']) for c in pres.values() for i in c); out, t = [], A
    for w0, w1 in iv:
        if w0 - t > 60: out.append(w0 - t)
        t = max(t, w1)
    if Z - t > 60: out.append(Z - t)
    return len(out), round(sum(out) / 60, 1)

rows = []
for d in sorted((ROOT / 'work' / 'rescue').glob('*_2026-*')):
    client, day = d.name.split('_'); base = ROOT / 'source' / client / day
    tl = json.load(open(base / 'timeline.json')); A, Z = sod(tl['first_seen']), sod(tl['last_seen'])
    b, a = json.load(open(d / 'presence.before.json')), json.load(open(base / 'presence.json'))
    rv = json.load(open(d / 'review.json'))
    resc = sum(1 for v in a.values() for i in v if i['verified'] == 'rescued')
    rows.append({'client': client, 'day': day, 'span_min': round((Z - A) / 60, 1), 'reviewed': rv['reviewed'], 'accepted': len(rv['accepted']),
                 'holes_before': holes(b, A, Z), 'holes_after': holes(a, A, Z), 'clips_before': sum(map(len, b.values())),
                 'clips_after': sum(map(len, a.values())), 'rescued_only_clips': resc})
json.dump(rows, open(ROOT / 'work' / 'rescue' / 'report.json', 'w'), indent=1)
for r in rows: print(r)
