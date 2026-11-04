"""Dense strip of one set for a manual rep count: repstrip.py CLIENT DAY SET_ID [SET_ID ...]
Samples the set (t0-1 .. t1+1) at up to 3 fps (max 60 tiles), 150 px tiles with the skeleton, 12 per row."""
import sys, json, pathlib, numpy as np, cv2
ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from pose_events import tile
client, day = sys.argv[1:3]; base = ROOT / 'source' / client / day
S = {s['id']: s for s in json.load(open(base / 'sets.json'))['sets']}
out = ROOT / 'work' / 'sets' / 'repcheck'; out.mkdir(parents=True, exist_ok=True)
for sid in sys.argv[3:]:
    s = S[sid]; clip = base / 'clips' / f"{s['clip']}.mp4"
    P = json.load(open(clip.with_suffix('.pose.json'))); F = P['frames']; fps = P['fps']
    a, b = s['t0'] - 1, s['t1'] + 1; n = int(min(60, (b - a) * 3)); ts = np.linspace(a, b, n)
    cap = cv2.VideoCapture(str(clip))
    tl = [tile(cap, F, fps, t, f'{t:.1f}', 150, 1.6) for t in ts]
    tl = [x if x is not None else np.zeros((150, 150, 3), np.uint8) for x in tl]
    while len(tl) % 12: tl.append(np.zeros((150, 150, 3), np.uint8))
    cv2.imwrite(str(out / f'{sid}.jpg'), np.vstack([np.hstack(tl[i:i + 12]) for i in range(0, len(tl), 12)]))
    print(sid, s['clip'], s['t0'], s['t1'], 'pose reps', s['reps'], 'rep_times', s['rep_times'], n, 'tiles')
