"""Phase J: find holes in the client library and rank candidate tracks that could fill them.

Hole = gap > 60 s inside [first_seen, last_seen] not covered by any presence interval (any camera).
Candidates = person tracks on cam101/cam201/cam401 overlapping a hole by >= 8 s that are not already
labelled (0/1/p). Ranking = CLIP-ReID classifier probability (rank_<cam>.json) + continuity with the
nearest confirmed box on the same camera. RTMPose runs on the candidate's 1 Hz crops (activity =
elbow/knee angle spread) and a review sheet (crops + skeleton) is written per day.

usage: holes.py CLIENT DAY [--top 3] [--minp 0.02]
out: work/rescue/<client>_<day>/{holes.json,cands.json,sheet_NN.jpg}
"""
import sys, os, json, pathlib, argparse, collections, math
import numpy as np, cv2

ROOT = pathlib.Path(__file__).resolve().parent
ap = argparse.ArgumentParser(); ap.add_argument('client'); ap.add_argument('day')
ap.add_argument('--top', type=int, default=3); ap.add_argument('--minp', type=float, default=0.02)
ap.add_argument('--min-overlap', type=float, default=8); ap.add_argument('--extra-p', type=float, default=None)
a = ap.parse_args()
base = ROOT / 'source' / a.client / a.day
out = ROOT / 'work' / 'rescue' / f'{a.client}_{a.day}'; out.mkdir(parents=True, exist_ok=True)
sod = lambda s: sum(int(v) * m for v, m in zip(s.split(':'), (3600, 60, 1)))
hms = lambda s: f'{int(s) // 3600:02d}:{int(s) % 3600 // 60:02d}:{int(s) % 60:02d}'
tl = json.load(open(base / 'timeline.json')); pres = json.load(open(base / 'presence.json'))
labels = json.load(open(base / 'labels.json')) if (base / 'labels.json').exists() else {}
A, Z = sod(tl['first_seen']), sod(tl['last_seen'])
iv = sorted((i['w0'], i['w1']) for c in pres.values() for i in c)
holes, t = [], A
for w0, w1 in iv:
    if w0 - t > 60: holes.append([t, w0])
    t = max(t, w1)
if Z - t > 60: holes.append([t, Z])
print(a.client, a.day, len(holes), 'holes', round(sum(h[1] - h[0] for h in holes) / 60, 1), 'min')

import onnxruntime as ort; ort.preload_dlls()
from rtmlib import RTMPose
import pose2d
pose = RTMPose(pose2d.MODEL, model_input_size=(288, 384), backend='onnxruntime', device='cuda')

cands = []
for cam in ('cam101', 'cam201', 'cam401'):
    tj = base / 'tracks' / cam / 'tracks.json'
    if not tj.exists(): continue
    rows = json.load(open(tj))['rows']
    rk = base / 'matches' / f'rank_{cam}.json'
    tprob = {int(k): v for k, v in json.load(open(rk))['track_prob'].items()} if rk.exists() else {}
    lab = labels.get(cam, {})
    by = collections.defaultdict(list)
    for r in rows: by[r[0]].append(r)
    conf_rows = sorted((r for r in rows if lab.get(str(r[0])) == 1), key=lambda r: r[1])
    ct = np.array([r[1] for r in conf_rows]) if conf_rows else np.array([])
    for hi, (h0, h1) in enumerate(holes):
        hc = []
        for tid, R in by.items():
            if str(tid) in lab: continue
            ins = [r for r in R if h0 - 5 <= r[1] <= h1 + 5]
            if len(ins) / 5 < a.min_overlap: continue
            p = tprob.get(tid, 0.0)
            if p < a.minp: continue
            # continuity: nearest confirmed box in time (same camera) within 60 s of either end
            cont = None
            for e in (ins[0], ins[-1]):
                if len(ct):
                    j = int(np.argmin(np.abs(ct - e[1])))
                    if abs(ct[j] - e[1]) < 60:
                        cb = conf_rows[j]; bh = max(1, cb[5] - cb[3])
                        d = math.hypot((cb[2] + cb[4] - e[2] - e[4]) / 2, (cb[3] + cb[5] - e[3] - e[5]) / 2) / bh
                        cont = d if cont is None else min(cont, d)
            hc.append({'cam': cam, 'tid': tid, 'hole': hi, 't0': ins[0][1], 't1': ins[-1][1], 'secs': round(len(ins) / 5, 1),
                       'prob': round(p, 3), 'cont': None if cont is None else round(cont, 2),
                       'box_h': round(float(np.median([r[5] - r[3] for r in ins])))})
        hc.sort(key=lambda c: -(c['prob'] + (0.3 if c['cont'] is not None and c['cont'] < 1 else 0)))
        if a.extra_p is None: cands += hc[:a.top]
        else: cands += [c for c in hc[a.top:] if c['prob'] >= a.extra_p]
print(len(cands), 'candidates')


def pose_crop(img):
    h, w = img.shape[:2]; pad = int(max(h, w) * 0.15)
    big = cv2.copyMakeBorder(img, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=(0, 0, 0))
    kp, sc = pose(big, bboxes=[[0, 0, w + 2 * pad, h + 2 * pad]])
    return kp[0] - pad, sc[0]


rows_img = []
for k, c in enumerate(cands):
    cd = base / 'tracks' / c['cam'] / 'crops'
    crops = sorted(p for p in cd.glob(f"{c['tid']:06d}_*.jpg") if c['t0'] - 1 <= int(p.name[7:13]) / 10 <= c['t1'] + 1)
    angs, tiles = [], []
    for p in crops:
        img = cv2.imread(str(p)); kp, sc = pose_crop(img)
        a_ = {nm: (pose2d.angle(kp[i], kp[j], kp[l]) if min(sc[i], sc[j], sc[l]) > 0.3 else None) for nm, (i, j, l) in pose2d.ANG.items()}
        angs.append(a_)
    def spread(nm):
        v = [x[nm] for x in angs if x[nm] is not None]
        return float(np.std(v)) if len(v) > 5 else 0.0
    c['elbow_sd'] = round(max(spread('l_elbow'), spread('r_elbow')), 1)
    c['knee_sd'] = round(max(spread('l_knee'), spread('r_knee')), 1)
    pick = [crops[i] for i in np.linspace(0, len(crops) - 1, min(10, len(crops))).round().astype(int)] if crops else []
    for p in pick:
        img = cv2.imread(str(p)); kp, sc = pose_crop(img)
        for i, j in [(5, 7), (7, 9), (6, 8), (8, 10), (5, 6), (5, 11), (6, 12), (11, 12), (11, 13), (13, 15), (12, 14), (14, 16)]:
            if sc[i] > .3 and sc[j] > .3: cv2.line(img, tuple(map(int, kp[i])), tuple(map(int, kp[j])), (0, 200, 255), 1)
        t = cv2.resize(img, (110, 200)); cv2.putText(t, hms(int(p.name[7:13]) / 10)[3:], (2, 195), 0, .35, (255, 255, 0), 1)
        tiles.append(t)
    while len(tiles) < 10: tiles.append(np.zeros((200, 110, 3), np.uint8))
    head = np.zeros((200, 230, 3), np.uint8)
    for li, s in enumerate([f"#{k} {c['cam']} tid {c['tid']}", f"{hms(c['t0'])}-{hms(c['t1'])[3:]}", f"{c['secs']}s hole {c['hole']}",
                            f"p {c['prob']} cont {c['cont']}", f"elbow sd {c['elbow_sd']} knee {c['knee_sd']}", f"box h {c['box_h']}"]):
        cv2.putText(head, s, (4, 22 + li * 28), 0, .5, (255, 255, 255), 1)
    rows_img.append(np.hstack([head] + tiles))
for i in range(0, len(rows_img), 6):
    cv2.imwrite(str(out / f"{'x' if a.extra_p is not None else ''}sheet_{i // 6:02d}.jpg"), np.vstack(rows_img[i:i + 6]))
json.dump({'holes': [[hms(h0), hms(h1), round((h1 - h0) / 60, 1)] for h0, h1 in holes]}, open(out / 'holes.json', 'w'), indent=1)
json.dump(cands, open(out / ('xcands.json' if a.extra_p is not None else 'cands.json'), 'w'), indent=1)
print('wrote', out, len(rows_img), 'rows')
