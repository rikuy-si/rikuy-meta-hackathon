"""Phase C gate: compare embedding models on a labeled client-day camera (zero-shot, reference only).

usage: modelcmp.py CLIENT DAY CAM [models...]
Scores every track (>= 3 crops) by its similarity to the reference crops (same rule as match.py, no query
expansion) and reports precision@10/@20/@50 and average precision against labels.json (label 1 = positive;
0 and unlabeled = negative, so the numbers are lower bounds). Writes source/<client>/<day>/matches/modelcmp_<cam>.json.
"""
import sys, json, pathlib
import numpy as np
import embed

ROOT = pathlib.Path(__file__).resolve().parent
client, day, cam = sys.argv[1:4]
models = sys.argv[4:] or ['clipreid', 'osnet', 'plip', 'dinov2']
base = ROOT / 'source' / client / day
lab = json.load(open(base / 'labels.json')).get(cam, {})
ref = sorted((base / 'reference' / 'crops').glob('*.jpg'))
ref_tracks = {p.name[:6] for p in ref} if all(p.name[:6].isdigit() for p in ref) else set()
out = {}
for m in models:
    z = np.load(ROOT / 'work' / 'emb' / f'{client}_{day}_{cam}_{m}.npz')
    E, names = z['E'], z['names']
    tids = np.array([int(n[:6]) for n in names])
    R = embed.get(m)(ref)
    s = np.sort(E @ R.T, axis=1)[:, -5:].mean(1)
    sc = {}
    for t in np.unique(tids):
        if f'{t:06d}' in ref_tracks:
            continue  # the reference tracks themselves are excluded
        v = np.sort(s[tids == t])[::-1]
        sc[int(t)] = float(v[:max(1, (len(v) + 1) // 2)].mean())
    order = sorted(sc, key=sc.get, reverse=True)
    rel = np.array([1 if lab.get(str(t)) == 1 else 0 for t in order])
    prec = np.cumsum(rel) / np.arange(1, len(rel) + 1)
    ap = float((prec * rel).sum() / max(1, rel.sum()))
    out[m] = {'P@10': float(rel[:10].mean()), 'P@20': float(rel[:20].mean()), 'P@50': float(rel[:50].mean()), 'AP': ap,
              'positives': int(rel.sum()), 'tracks': len(order)}
    print(f"{m:9s} P@10={out[m]['P@10']:.2f} P@20={out[m]['P@20']:.2f} P@50={out[m]['P@50']:.2f} AP={ap:.3f} (positives {rel.sum()} of {len(order)})", flush=True)
json.dump(out, open(base / 'matches' / f'modelcmp_{cam}.json', 'w'), indent=1)
