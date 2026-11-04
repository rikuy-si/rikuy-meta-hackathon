"""Phase F: per-visit activity timeline from the source library.

usage: timeline.py CLIENT DAY
Reads source/<client>/<day>/presence.json, clips/*.track.json, zones/zones.json.
For every second the client is seen, choose the best camera (largest box, gym cameras preferred over the
reception camera) and its zone (foot point = bottom-centre of the box). Consecutive seconds in the same
zone (gaps <= 45 s) form blocks. Each block gets an activity label from the motion of the foot point:
'ejercicio' (mostly stationary: series at a station) or 'desplazamiento' (walking between stations).
Writes source/<client>/<day>/timeline.json and prints a summary.
"""
import sys, json, pathlib, collections
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent
client, day = sys.argv[1], sys.argv[2]
base = ROOT / 'source' / client / day
Z = json.load(open(ROOT / 'zones' / 'zones.json'))
presence = json.load(open(base / 'presence.json'))


def inside(pt, poly):
    x, y = pt; n = len(poly); c = False
    for i in range(n):
        x1, y1 = poly[i]; x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-9) + x1:
            c = not c
    return c


def zone(cam, box):
    pt = ((box[0] + box[2]) / 2, box[3])
    for z in Z[cam]:
        if inside(pt, z['poly']):
            return z
    return Z[cam][-1]


def hms(s):
    s = int(round(s)); return f'{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}'


obs = collections.defaultdict(list)  # second -> [(cam, box, h)]
for cam, ivs in presence.items():
    for iv in ivs:
        tj = json.load(open(base / 'clips' / f"{iv['name']}.track.json"))
        for b in tj['boxes']:
            h = b['box'][3] - b['box'][1]
            obs[int(b['sod'])].append((cam, b['box'], h * (0.5 if cam == 'cam301' else 1.0), b['status']))
secs = sorted(obs)
if not secs:
    sys.exit('no observations')
per_sec = []
for s in secs:
    cam, box, h, st = max(obs[s], key=lambda o: o[2])
    z = zone(cam, box)
    per_sec.append({'s': s, 'cam': cam, 'box': box, 'zone': z['id'], 'label': z['label'], 'cams': sorted({o[0] for o in obs[s]})})

blocks = []
for p in per_sec:
    if blocks and p['zone'] == blocks[-1]['zone'] and p['s'] - blocks[-1]['t1'] <= 45:
        blocks[-1]['t1'] = p['s']; blocks[-1]['pts'].append(p)
    else:
        blocks.append({'zone': p['zone'], 'label': p['label'], 't0': p['s'], 't1': p['s'], 'pts': [p]})
# merge tiny blocks (< 20 s) into the neighbour so the timeline reads like a routine, not jitter
merged = []
for b in blocks:
    if merged and (b['t1'] - b['t0'] < 20) and b['t0'] - merged[-1]['t1'] <= 45:
        merged[-1]['t1'] = b['t1']; merged[-1]['pts'] += b['pts']
    else:
        merged.append(b)
m2 = []
for b in merged:
    if m2 and m2[-1]['label'] == b['label'] and b['t0'] - m2[-1]['t1'] <= 60:
        m2[-1]['t1'] = b['t1']; m2[-1]['pts'] += b['pts']
    else:
        m2.append(b)
merged = m2
out = []
for b in merged:
    cams = collections.Counter(p['cam'] for p in b['pts'])
    best = cams.most_common(1)[0][0]
    pts = [p for p in b['pts'] if p['cam'] == best]
    feet = np.array([((p['box'][0] + p['box'][2]) / 2, p['box'][3]) for p in pts])
    hs = np.array([p['box'][3] - p['box'][1] for p in pts])
    ts = np.array([p['s'] for p in pts])
    if len(pts) > 1:
        sp = np.linalg.norm(np.diff(feet, axis=0), axis=1) / np.maximum(np.diff(ts), 1) / np.maximum(hs[1:], 1)
        moving = float(np.mean(sp > 0.25))
    else:
        moving = 1.0
    zl = collections.Counter((p['zone'], p['label']) for p in b['pts']).most_common(1)[0][0]
    out.append({'t0': b['t0'], 't1': b['t1'], 'start': hms(b['t0']), 'end': hms(b['t1']), 'duration_s': b['t1'] - b['t0'],
                'zone': zl[0], 'label': zl[1], 'best_camera': best, 'cameras': dict(cams),
                'activity': 'desplazamiento' if moving > 0.5 or zl[0] == 'recepcion' else 'ejercicio',
                'seen_s': len(b['pts']), 'mean_box_h': int(hs.mean()) if len(hs) else 0})
entry = presence.get('cam301', [])
tot = collections.Counter()
for b in out:
    tot[b['label']] += b['duration_s']
res = {'client': client, 'day': day, 'first_seen': hms(secs[0]), 'last_seen': hms(secs[-1]),
       'span_min': round((secs[-1] - secs[0]) / 60, 1), 'seen_min': round(len(secs) / 60, 1),
       'reception_intervals': [(i['start'], i['end']) for i in entry],
       'zone_minutes': {k: round(v / 60, 1) for k, v in tot.most_common()}, 'blocks': out}
json.dump(res, open(base / 'timeline.json', 'w'), indent=1, ensure_ascii=False)
print(f"{client} {day}: first {res['first_seen']} last {res['last_seen']} span {res['span_min']} min, seen {res['seen_min']} min")
for b in out:
    print(f"  {b['start']}-{b['end']} {b['duration_s']:5d}s {b['label']:<22} {b['activity']:<15} {b['best_camera']}")
print(' zones:', res['zone_minutes'])
