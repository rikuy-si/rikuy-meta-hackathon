"""Phase I/K: day-level set list + one review row per set.

usage: sets_day.py CLIENT DAY [--min-score 0.5] [--sheets]
Reads clips/<clip>.events.json (pose_events.py) for the clips listed in presence.json, converts set times
to seconds of day, merges the same set seen by two cameras (time overlap > 50 % of the shorter one; the
higher lifting score wins, the others are kept as `alts`), recomputes rest_before across clips, and writes
source/<client>/<day>/sets.json. With --sheets, writes work/sets/<client>_<day>/sets_NN.jpg: one row per
reviewable set (score >= --min-score): pre, first rep, middle rep, slowest rep, last rep, +2 s after.
"""
import sys, json, pathlib, argparse
import numpy as np, cv2

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from pose_events import tile

ap = argparse.ArgumentParser(); ap.add_argument('client'); ap.add_argument('day')
ap.add_argument('--min-score', type=float, default=0.5); ap.add_argument('--sheets', action='store_true')
a = ap.parse_args()
base = ROOT / 'source' / a.client / a.day
hms = lambda s: f'{int(s) // 3600:02d}:{int(s) % 3600 // 60:02d}:{int(s) % 60:02d}'
pres = json.load(open(base / 'presence.json'))
raw, missing = [], []
for cam, ivs in pres.items():
    for iv in ivs:
        c = base / 'clips' / f"{iv['name']}.mp4"; ev = c.with_suffix('.events.json')
        if not ev.exists():
            missing.append(iv['name']); continue
        E = json.load(open(ev)); w0 = json.load(open(c.with_suffix('.track.json')))['w0']
        for s in E['sets']:
            raw.append({**s, 'clip': iv['name'], 'camera': cam, 'verified': iv['verified'],
                        'sod0': round(w0 + s['t0'], 1), 'sod1': round(w0 + s['t1'], 1)})
raw.sort(key=lambda s: -s['score'])
kept = []
for s in raw:
    for k in kept:
        ov = min(s['sod1'], k['sod1']) - max(s['sod0'], k['sod0'])
        if ov > 0.5 * min(s['sod1'] - s['sod0'], k['sod1'] - k['sod0']):
            k['alts'].append({x: s[x] for x in ('clip', 'camera', 't0', 't1', 'reps', 'score')}); break
    else:
        kept.append({**s, 'alts': []})
kept.sort(key=lambda s: s['sod0'])
for i, s in enumerate(kept):
    s['id'] = f"{a.client[0].upper()}{a.day[-2:]}-{i + 1:03d}"; s['start'] = hms(s['sod0'])
    s['rest_before_day'] = round(s['sod0'] - kept[i - 1]['sod1'], 1) if i else None
    s['review'] = s['score'] >= a.min_score
json.dump({'client': a.client, 'day': a.day, 'min_score_review': a.min_score, 'n_raw': len(raw), 'missing_events': missing,
           'sets': kept}, open(base / 'sets.json', 'w'), indent=1)
rv = [s for s in kept if s['review']]
print(a.client, a.day, 'raw', len(raw), 'merged', len(kept), 'reviewable', len(rv), 'missing events', len(missing))

if a.sheets:
    out = ROOT / 'work' / 'sets' / f'{a.client}_{a.day}'; out.mkdir(parents=True, exist_ok=True)
    for p in out.glob('*.jpg'): p.unlink()
    rows = []
    for s in rv:
        clip = base / 'clips' / f"{s['clip']}.mp4"
        P = json.load(open(clip.with_suffix('.pose.json'))); F = P['frames']; fps = P['fps']
        R = s['rep_times']; d = s['rep_dur']
        slow = R[int(np.argmax(d)) + 1] if d else R[-1]
        keys = [(R[0], 'rep1'), (R[0] + (d[0] if d else 1) / 2, 'rep1 mid'), (R[len(R) // 2], f'rep{len(R) // 2 + 1}'), (slow, 'slowest'),
                (s['t1'] + 2, '+2s')]
        cap = cv2.VideoCapture(str(clip))
        tl = [tile(cap, F, fps, t, f'{l} {t:.0f}s', 240, 2.2) for t, l in keys]
        tl = [x if x is not None else np.zeros((240, 240, 3), np.uint8) for x in tl]
        head = np.zeros((240, 230, 3), np.uint8)
        for li, txt in enumerate([s['id'], f"{s['start']} {s['camera']}", f"{s['reps']} reps {s['driver']}",
                                  f"rom {s['rom']} slow x{s['slowdown']}", f"score {s['score']} {s['verified']}",
                                  f"alts {len(s['alts'])} cel {s['celebration']}"]):
            cv2.putText(head, txt, (5, 26 + li * 36), 0, .55, (255, 255, 255), 1)
        rows.append(np.hstack([head] + tl))
    for i in range(0, len(rows), 6):
        cv2.imwrite(str(out / f'sheet_{i // 6:02d}.jpg'), np.vstack(rows[i:i + 6]))
    print('sheets', (len(rows) + 5) // 6, out)
