"""review.py CLIENT DAY CAM OUT.jpg (--model M --top N [--key score|score_qe] | --tids t1 t2 ...)
Contact sheet: one row per track = label (tid, time, score) + up to 8 crops + reference strip on top."""
import sys, json, pathlib, argparse, collections
import cv2, numpy as np

ROOT = pathlib.Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument('client'); ap.add_argument('day'); ap.add_argument('cam'); ap.add_argument('out')
ap.add_argument('--model'); ap.add_argument('--top', type=int, default=15); ap.add_argument('--key', default='score')
ap.add_argument('--tids', nargs='*', type=int); ap.add_argument('--skip', type=int, default=0)
ap.add_argument('--ncrops', type=int, default=8)
a = ap.parse_args()
base = ROOT / 'source' / a.client / a.day
cd = base / 'tracks' / a.cam / 'crops'
TW, TH = 80, 160


def hms(s):
    s = int(s); return f'{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}'


def tile(p):
    im = cv2.imread(str(p)); return cv2.resize(im, (TW, TH))


scores = json.load(open(base / 'matches' / f'{a.model}.json'))[a.cam] if a.model else {}
if a.tids:
    tids = a.tids
else:
    tids = [int(t) for t in sorted(scores, key=lambda t: scores[t][a.key], reverse=True)[a.skip:a.skip + a.top]]
g = collections.defaultdict(list)
for p in sorted(cd.glob('*.jpg')):
    g[int(p.name[:6])].append(p)
rows = []
ref = sorted((base / 'reference' / 'crops').glob('*.jpg'))
reflab = 'REFERENCE'
if not ref:  # cross-day search: show the most recent other day's reference
    for od in sorted((ROOT / 'source' / a.client).glob('*/reference/crops'), reverse=True):
        ref = sorted(od.glob('*.jpg')); reflab = 'REF ' + od.parts[-3][5:]; break
ref = [ref[i] for i in np.linspace(0, len(ref) - 1, a.ncrops).round().astype(int)]
lab = np.zeros((TH, 200, 3), np.uint8); cv2.putText(lab, reflab, (8, 80), 0, 0.7, (0, 255, 255), 2)
rows.append(np.hstack([lab] + [tile(p) for p in ref]))
for t in tids:
    ps = g.get(t, [])
    if not ps:
        continue
    sel = [ps[i] for i in np.linspace(0, len(ps) - 1, min(a.ncrops, len(ps))).round().astype(int)]
    lab = np.zeros((TH, 200, 3), np.uint8)
    s = scores.get(str(t), {})
    t0 = int(ps[0].name[7:13]) / 10; t1 = int(ps[-1].name[7:13]) / 10
    for i, txt in enumerate([f'#{t}', f'{hms(t0)}', f'-{hms(t1)}', f'n={len(ps)}', f"s={s.get(a.key, 0):.3f}" if s else '']):
        cv2.putText(lab, txt, (8, 28 + i * 28), 0, 0.65, (255, 255, 255), 2)
    ims = [tile(p) for p in sel] + [np.zeros((TH, TW, 3), np.uint8)] * (a.ncrops - len(sel))
    rows.append(np.hstack([lab] + ims))
cv2.imwrite(a.out, np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 85])
print('wrote', a.out, len(rows) - 1, 'tracks')
