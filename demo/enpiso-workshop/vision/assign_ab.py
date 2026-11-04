#!/usr/bin/env python3
"""Associate anonymous tracklets to A/B using appearance (DINOv2) galleries seeded from the
user's reference frame, with temporal exclusivity. Unresolved tracklets stay unassigned.
No face recognition; labels are within-video anonymous identities."""
import gzip, json, glob, collections
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
VA = ROOT / "enpiso/video-review/media/vision-analysis"
OUT = VA / "ab"; OUT.mkdir(parents=True, exist_ok=True)
REF_T = 129.0
REF = {"A": [355 / 1440, 520 / 810, 630 / 1440, 810 / 810], "B": [860 / 1440, 355 / 810, 1085 / 1440, 810 / 810]}
SIM_HI, SIM_LO, MARGIN = 0.80, 0.72, 0.04

z = np.load(VA / "reid/track-embeddings.npz")
keys, embs = z["keys"], z["embs"].astype(np.float32)
by_tid = collections.defaultdict(list)
for (rec, fr, tid), e in zip(keys, embs):
    by_tid[int(tid)].append(e)

dets = collections.defaultdict(list)  # tid -> [(rec, frame, t, box, conf)]
for f in sorted(glob.glob(str(VA / "tracks/full5-rec*.jsonl.gz"))):
    for l in gzip.open(f, "rt"):
        d = json.loads(l)
        for p in d["p"]:
            if p[0] >= 0:
                dets[p[0]].append((d["rec"], d["frame"], d["t"], p[1:5], p[5]))
span = {t: (v[0][2], v[-1][2]) for t, v in dets.items()}


def iou(a, b):
    x1, y1, x2, y2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    i = max(0, x2 - x1) * max(0, y2 - y1)
    return i / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i)

seed = {}
for lab, rb in REF.items():
    best = max(((iou(rb, b), tid) for tid, v in dets.items() for (_, _, t, b, _) in v if abs(t - REF_T) < 0.11), default=(0, None))
    seed[lab] = best[1]; print("seed", lab, best)

gallery = {lab: [by_tid[tid][i] for i in range(0, len(by_tid[tid]), max(1, len(by_tid[tid]) // 40))] for lab, tid in seed.items()}
assign = {seed["A"]: ("A", 1.0, "seed"), seed["B"]: ("B", 1.0, "seed")}


def score(tid, lab):
    G = np.stack(gallery[lab]); E = np.stack(by_tid[tid])
    S = E @ G.T
    return float(np.median(S.max(1)))

cands = [t for t in by_tid if len(by_tid[t]) >= 3 and t not in assign]
for it in range(4):
    sc = {t: {lab: score(t, lab) for lab in "AB"} for t in cands if t not in assign}
    added = 0
    for t, s in sorted(sc.items(), key=lambda kv: -max(kv[1].values())):
        lab = max(s, key=s.get); other = "B" if lab == "A" else "A"
        if s[lab] < SIM_HI or s[lab] - s[other] < MARGIN:
            continue
        # temporal exclusivity: no overlap with an already-assigned same-label tracklet
        a0, a1 = span[t]
        ov = sum(max(0, min(a1, span[u][1]) - max(a0, span[u][0])) for u, (l, *_ ) in assign.items() if l == lab)
        if ov > 0.2 * (a1 - a0 + 1e-6):
            continue
        assign[t] = (lab, s[lab], f"iter{it}")
        gallery[lab].extend(by_tid[t][:: max(1, len(by_tid[t]) // 10)]); added += 1
    print("iter", it, "added", added)
    if not added:
        break

# low-confidence candidates (reported, not used as A/B evidence)
uncertain = {}
for t in cands:
    if t in assign:
        continue
    s = {lab: score(t, lab) for lab in "AB"}; lab = max(s, key=s.get)
    if s[lab] >= SIM_LO:
        uncertain[t] = (lab, s[lab])

MANUAL_UNCERTAIN = {862, 643}  # QA: back view, identity not visually confirmable
# Reviewer decisions from QA contact sheets (qa-uncertain-*.jpg, qa-gap-*.jpg), 2026-11-01/02
MANUAL_CONFIRM = json.load(open(OUT / "manual-review.json")) if (OUT / "manual-review.json").exists() else {"confirm": {}, "reject": []}
for t, lab in MANUAL_CONFIRM["confirm"].items():
    t = int(t)
    if t in dets:
        uncertain.pop(t, None); assign[t] = (lab, 1.0, "manual")
for t in MANUAL_CONFIRM["reject"]:
    assign.pop(int(t), None); uncertain.pop(int(t), None)
# gap candidates: unassigned tracklets inside A/B coverage gaps (>8 s) with weak appearance similarity
cover = {lab: sorted({tt for t, (l, *_ ) in assign.items() if l == lab for (_, _, tt, _, _) in dets[t]}) for lab in "AB"}
gapc = {}
for lab in "AB":
    v = cover[lab]
    for a_, b_ in zip(v, v[1:]):
        if b_ - a_ <= 8:
            continue
        for t in by_tid:
            if t in assign or t in MANUAL_CONFIRM["reject"] or str(t) in map(str, MANUAL_CONFIRM["reject"]):
                continue
            if span[t][1] < a_ or span[t][0] > b_ or len(dets[t]) < 5:
                continue
            sc_ = score(t, lab)
            if sc_ >= 0.6 and str(t) not in gapc:
                gapc[str(t)] = {"label_guess": lab, "sim": round(sc_, 3), "t0": span[t][0], "t1": span[t][1], "n": len(dets[t])}
for t in MANUAL_UNCERTAIN:
    if t in assign:
        l, s_, _ = assign.pop(t); uncertain[t] = (l, s_)
# per-frame dedupe: one detection per label per frame, prefer spatial continuity
per = collections.defaultdict(list)
for t, (lab, sc_, why) in assign.items():
    for rec, fr, tt, b, cf in dets[t]:
        per[(lab, tt)].append((t, rec, fr, b, cf, sc_))
dups = 0; last = {}
with gzip.open(OUT / "ab-detections.jsonl.gz", "wt") as f:
    for (lab, tt) in sorted(per, key=lambda k: k[1]):
        c = per[(lab, tt)]
        if len(c) > 1:
            dups += 1
            pb = last.get(lab)
            c.sort(key=lambda x: -iou(x[3], pb) if pb else -x[5])
        t, rec, fr, b, cf, sc_ = c[0]; last[lab] = b
        f.write(json.dumps({"rec": rec, "frame": fr, "t": tt, "label": lab, "track": t, "box": b, "det_conf": cf, "assoc_sim": round(sc_, 3)}) + "\n")
print("frames with duplicate same-label detections resolved:", dups)

cov = {}
for lab in "AB":
    ts = sorted({tt for t, (l, *_ ) in assign.items() if l == lab for (_, _, tt, _, _) in dets[t]})
    cov[lab] = {"tracklets": sum(1 for v in assign.values() if v[0] == lab), "samples": len(ts),
                "coverage_pct_of_37721": round(100 * len(ts) / 37721, 1)}
summary = {"seed_tracks": seed, "thresholds": {"hi": SIM_HI, "lo": SIM_LO, "margin": MARGIN}, "coverage": cov,
           "assigned": {str(t): {"label": l, "sim": round(s, 3), "how": w, "t0": span[t][0], "t1": span[t][1], "n": len(dets[t])} for t, (l, s, w) in assign.items()},
           "gap_candidates": gapc, "uncertain": {str(t): {"label_guess": l, "sim": round(s, 3), "t0": span[t][0], "t1": span[t][1], "n": len(dets[t])} for t, (l, s) in uncertain.items()}}
json.dump(summary, open(OUT / "ab-assignment.json", "w"), indent=1)
print(json.dumps(cov))
