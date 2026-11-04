"""Phase C (iterative, human-in-the-loop): rank unlabeled tracks with a per-camera classifier.

usage: rank.py CLIENT DAY CAM [--model clipreid] [--top 16] [--sheet OUT.jpg]
labels: source/<client>/<day>/labels.json  {cam: {tid: 1 | 0 | "p"}}   (1 = client, 0 = not, p = partial/ID switch)
Positives = reference crops + crops of tracks labeled 1 (all cameras, current camera weighted x3);
negatives = crops of tracks labeled 0 + a random background sample of the camera's crops.
Writes source/<client>/<day>/matches/rank_<cam>.json with per-track probability and per-crop scores.
"""
import sys, json, pathlib, argparse, subprocess, collections
import numpy as np
from sklearn.linear_model import LogisticRegression

ROOT = pathlib.Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument('client'); ap.add_argument('day'); ap.add_argument('cam')
ap.add_argument('--model', default='clipreid'); ap.add_argument('--top', type=int, default=16)
ap.add_argument('--sheet'); ap.add_argument('--include-labeled', action='store_true')
ap.add_argument('--pos-days', nargs='*', default=[], help='other days of the same client whose positives are added (cross-day prior)')
ap.add_argument('--t0', type=float, default=0); ap.add_argument('--t1', type=float, default=86400)
a = ap.parse_args()
base = ROOT / 'source' / a.client / a.day
lab_path = base / 'labels.json'
labels = json.load(open(lab_path)) if lab_path.exists() else {}
emb = ROOT / 'work' / 'emb'


def load(cam):
    z = np.load(emb / f'{a.client}_{a.day}_{cam}_{a.model}.npz')
    tids = np.array([int(n[:6]) for n in z['names']])
    return z['E'], tids, z['names']


import embed
refp = sorted((base / 'reference' / 'crops').glob('*.jpg'))
pos, neg = ([embed.get(a.model)(refp)] if refp else []), []
for cam, lab in labels.items():
    if not (emb / f'{a.client}_{a.day}_{cam}_{a.model}.npz').exists():
        continue
    E, tids, _ = load(cam)
    for t, v in lab.items():
        sel = E[tids == int(t)]
        if v == 1:
            pos += [sel] * (3 if cam == a.cam else 1)
        elif v == 0:
            neg.append(sel)
for od in a.pos_days:
    ob = ROOT / 'source' / a.client / od
    if (ob / 'reference' / 'crops').exists():
        pos.append(embed.get(a.model)(sorted((ob / 'reference' / 'crops').glob('*.jpg'))))
    olab = json.load(open(ob / 'labels.json')) if (ob / 'labels.json').exists() else {}
    for cam, lab in olab.items():
        f = emb / f'{a.client}_{od}_{cam}_{a.model}.npz'
        if f.exists():
            z = np.load(f); tt = np.array([int(n[:6]) for n in z['names']])
            keep = np.isin(tt, [int(t) for t, v in lab.items() if v == 1])
            pos.append(z['E'][keep])
E, tids, names = load(a.cam)
rng = np.random.default_rng(0)
lab = labels.get(a.cam, {})
bg_idx = [i for i in rng.permutation(len(E))[:3000] if str(tids[i]) not in lab]
neg.append(E[bg_idx])
P, N = np.concatenate(pos), np.concatenate(neg)
X = np.concatenate([P, N]); y = np.r_[np.ones(len(P)), np.zeros(len(N))]
clf = LogisticRegression(C=1.0, class_weight='balanced', max_iter=2000).fit(X, y)
p = clf.predict_proba(E)[:, 1]
tsec = np.array([int(n[7:13]) / 10 for n in names])
res = {}
for t in np.unique(tids[(tsec >= a.t0) & (tsec <= a.t1)]):
    pc = np.sort(p[tids == t])[::-1]
    res[int(t)] = float(pc[:max(1, (len(pc) + 1) // 2)].mean())
json.dump({'track_prob': res, 'crop_prob': {n: round(float(v), 4) for n, v in zip(names, p)}},
          open(base / 'matches' / f'rank_{a.cam}.json', 'w'))
cand = [t for t in sorted(res, key=res.get, reverse=True) if a.include_labeled or str(t) not in lab]
print('pos crops', len(P), 'neg crops', len(N), 'labeled', len(lab))
print('next:', [(t, round(res[t], 3)) for t in cand[:a.top]])
print('prob>0.5 unlabeled:', sum(1 for t in cand if res[t] > 0.5), ' labeled-positive:', sum(1 for v in lab.values() if v == 1))
if a.sheet:
    subprocess.run([sys.executable, str(ROOT / 'review.py'), a.client, a.day, a.cam, a.sheet, '--tids', *map(str, cand[:a.top])], check=True)
