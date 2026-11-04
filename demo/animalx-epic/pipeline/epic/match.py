"""Phase C: score every track of a client-day against the day reference, per model.

usage: match.py CLIENT DAY [models...]
Reads  source/<client>/<day>/reference/crops/*.jpg and source/<client>/<day>/tracks/camXXX/{tracks.json,crops/}
Writes source/<client>/<day>/matches/<model>.json  {cam: {tid: {score, score_qe, n, t0, t1}}}
Embeddings are cached in work/emb/<client>_<day>_<cam>_<model>.npz.
Scoring: crop-level sim = mean of top-5 sims to the reference set; track score = mean of the best half of
its (up to 12, evenly spaced) crops. Query expansion: the top tracks of each camera (score >= QE_MIN and
clearly above the camera's median) are added to that camera's reference and all tracks rescored.
"""
import sys, json, pathlib, collections
import numpy as np
import embed

ROOT = pathlib.Path(__file__).resolve().parent
client, day = sys.argv[1], sys.argv[2]
models = sys.argv[3:] or ['clipreid', 'osnet', 'plip', 'dinov2']
base = ROOT / 'source' / client / day
ref_paths = sorted((base / 'reference' / 'crops').glob('*.jpg'))
MIN_CROPS, PER_TRACK, QE_TOP = 3, 12, 3
(ROOT / 'work' / 'emb').mkdir(parents=True, exist_ok=True)
(base / 'matches').mkdir(parents=True, exist_ok=True)


def track_crops(cam_dir):
    g = collections.defaultdict(list)
    for p in sorted((cam_dir / 'crops').glob('*.jpg')):
        g[int(p.name[:6])].append(p)
    out = {}
    for tid, ps in g.items():
        if len(ps) < MIN_CROPS:
            continue
        idx = np.linspace(0, len(ps) - 1, min(PER_TRACK, len(ps))).round().astype(int)
        out[tid] = [ps[i] for i in sorted(set(idx))]
    return out


def crop_scores(E, R):
    s = E @ R.T
    k = min(5, R.shape[0])
    return np.sort(s, axis=1)[:, -k:].mean(1)


def track_score(cs):
    cs = np.sort(cs)[::-1]
    return float(cs[:max(1, (len(cs) + 1) // 2)].mean())


for m in models:
    enc = embed.get(m)
    R0 = enc(ref_paths) if ref_paths else None
    res = {}
    for cam_dir in sorted((base / 'tracks').glob('cam*')):
        if not (cam_dir / 'tracks.json').exists():
            continue
        cam = cam_dir.name
        tj = json.load(open(cam_dir / 'tracks.json'))
        span = collections.defaultdict(lambda: [1e9, -1e9])
        for tid, sod, *_ in tj['rows']:
            span[tid][0] = min(span[tid][0], sod); span[tid][1] = max(span[tid][1], sod)
        tc = track_crops(cam_dir)
        cache = ROOT / 'work' / 'emb' / f'{client}_{day}_{cam}_{m}.npz'
        flat = [(t, p) for t, ps in tc.items() for p in ps]
        names = np.array([p.name for _, p in flat])
        if cache.exists() and np.array_equal(np.load(cache)['names'], names):
            E = np.load(cache)['E']
        else:
            E = enc([p for _, p in flat]); np.savez(cache, E=E, names=names)
        tids = np.array([t for t, _ in flat])
        if not ref_paths:  # no reference yet (e.g. cross-day search): only cache embeddings
            print(m, cam, len(tc), 'tracks embedded (no reference)', flush=True); continue
        cs = crop_scores(E, R0)
        sc = {t: track_score(cs[tids == t]) for t in tc}
        # query expansion per camera
        vals = np.array(list(sc.values()))
        med, mad = np.median(vals), np.median(np.abs(vals - np.median(vals))) + 1e-6
        top = [t for t in sorted(sc, key=sc.get, reverse=True)[:QE_TOP] if (sc[t] - med) / mad > 6]
        if top:
            R1 = np.concatenate([R0, E[np.isin(tids, top)]])
            cs1 = crop_scores(E, R1)
            sq = {t: track_score(cs1[tids == t]) for t in tc}
        else:
            sq = sc
        res[cam] = {str(t): {'score': round(sc[t], 4), 'score_qe': round(sq[t], 4), 'z': round(float((sc[t] - med) / mad), 2),
                             'n': len(tc[t]), 't0': span[t][0], 't1': span[t][1]} for t in tc}
        print(m, cam, len(tc), 'tracks; top:', [(t, round(sc[t], 3)) for t in sorted(sc, key=sc.get, reverse=True)[:5]], 'qe seeds', top, flush=True)
    json.dump(res, open(base / 'matches' / f'{m}.json', 'w'))
    del enc
    import torch; torch.cuda.empty_cache()
