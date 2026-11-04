#!/usr/bin/env python3
"""Peri-event test: is 'hand in CP-device zone' enriched near CP candidate timestamps vs baseline?
Uses the 5 fps A/B hand keypoints. Baseline = all tracked samples of that person within 13:41-15:45 camera
excluding +/-90 s around any candidate. Also a circular-shift null (random offsets) for significance."""
import json, gzip
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
VA = ROOT / "enpiso/video-review/media/vision-analysis"
pl = json.load(open(ROOT / "enpiso/video-review/full-playlist.json"))
EVT = np.array([e["timeline"] for e in pl["events"]])
DEV = [0.555, 0.665, 0.610, 0.750]; PAD = 0.012
HAND = [9, 10] + list(range(91, 133))
res = {}
rng = np.random.default_rng(0)
for lab in "AB":
    z = np.load(VA / f"pose/pose-{lab}.npz")
    t = z["t"].astype(float); k2 = z["k2"].astype(np.float32)[:, HAND]; s = z["s"].astype(np.float32)[:, HAND]
    ok = s >= 0.3
    bx = z["box"].astype(np.float32)
    ix = np.clip(np.minimum(bx[:, 2], DEV[2]) - np.maximum(bx[:, 0], DEV[0]), 0, None)
    iy = np.clip(np.minimum(bx[:, 3], DEV[3]) - np.maximum(bx[:, 1], DEV[1]), 0, None)
    occ_all = ix * iy / ((DEV[2] - DEV[0]) * (DEV[3] - DEV[1])) >= 0.5
    inz_hand = ((k2[..., 0] >= DEV[0] - PAD) & (k2[..., 0] <= DEV[2] + PAD) & (k2[..., 1] >= DEV[1] - PAD) & (k2[..., 1] <= DEV[3] + PAD) & ok).any(1)
    tmax = EVT.max() + 120
    sel = t <= tmax
    t = t[sel]
    for metric, inz in (("hand_keypoint_in_device_zone", inz_hand[sel]), ("body_box_covers_device_zone", occ_all[sel])):
        # peri-event histogram, 2 s bins from -60 to +30
        bins = np.arange(-60, 32, 2)
        rel = (t[:, None] - EVT[None, :])
        hist = []
        for b0 in bins[:-1]:
            m = (rel >= b0) & (rel < b0 + 2)
            tot = m.sum(); hit = (m & inz[:, None]).sum()
            hist.append({"bin": int(b0), "samples": int(tot), "inZonePct": round(100 * hit / tot, 1) if tot else None})
        near = (np.abs(rel) <= 10).any(1)
        far = ~(np.abs(rel) <= 90).any(1)
        p_near = inz[near].mean(); p_base = inz[far].mean() if far.any() else float("nan")
        # null: shift all candidate times by random offsets within the window, recompute p_near
        null = []
        for _ in range(500):
            sh = EVT + rng.uniform(-1500, 1500)
            sh = np.clip(sh, 0, tmax)
            m = (np.abs(t[:, None] - sh[None, :]) <= 10).any(1)
            null.append(inz[m].mean() if m.any() else 0)
        null = np.array(null)
        res.setdefault(lab, {})[metric] = {"pInZone_within10s_of_candidate": round(float(p_near) * 100, 1),
                    "pInZone_baseline_gt90s_from_candidates": round(float(p_base) * 100, 1),
                    "enrichment_ratio": round(float(p_near / p_base), 2) if p_base else None,
                    "null_shift_mean_pct": round(float(null.mean()) * 100, 1),
                    "null_shift_p_value_one_sided": round(float((null >= p_near).mean()), 3),
                    "peri_event_hist": hist}
        print(lab, metric, {k: v for k, v in res[lab][metric].items() if k != "peri_event_hist"})
out = {"method": __doc__, "deviceZone": DEV, "pad": PAD, "score_threshold": 0.3, "results": res}
json.dump(out, open(VA / "analysis/peri-event.json", "w"), indent=1)
json.dump(out, open(VA / "web/peri-event.json", "w"), separators=(",", ":"))
