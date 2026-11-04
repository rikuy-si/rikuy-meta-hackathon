#!/usr/bin/env python3
"""Export compact per-recording overlay JSON for the browser app.

web/ab-recNN.json      A/B boxes at 5 fps (coords x1000 normalized to frame).
web/pose-recNN.json    A/B 2D keypoints (65 = body17+feet6+hands42, x10000), scores (0-9),
                       3D body keypoints (23, crop-space x1000, root-centred), head & torso yaw (deg).
web/material-recNN.json SAM 3 'garment' + 'person' polygons at 1 fps (x10000).
Frame indices are original source frame indices (15 fps) within each recording.
"""
import gzip, json, collections
from pathlib import Path
import numpy as np
import sys; sys.path.insert(0, str(Path(__file__).parent))
from material_filter import split

ROOT = Path(__file__).resolve().parents[1]
VA = ROOT / "enpiso/video-review/media/vision-analysis"
W = VA / "web"; W.mkdir(parents=True, exist_ok=True)
KP = list(range(0, 23)) + list(range(91, 133))  # COCO-WholeBody: body+feet, left hand, right hand


def dump(name, obj):
    (W / name).write_text(json.dumps(obj, separators=(",", ":")))

# --- A/B boxes
rows = collections.defaultdict(list)
for l in gzip.open(VA / "ab/ab-detections.jsonl.gz", "rt"):
    d = json.loads(l)
    rows[d["rec"]].append([d["frame"], d["label"], *[round(v * 1000) for v in d["box"]], d["track"], round(d["assoc_sim"] * 100)])
assign = json.load(open(VA / "ab/ab-assignment.json"))
manual = json.load(open(VA / "ab/manual-review.json"))
low = set(manual.get("back_view_lower_confidence", []))
for rec, rs in rows.items():
    rs.sort()
    dump(f"ab-rec{rec:02d}.json", {"rec": rec, "fps": 5, "cols": ["frame", "label", "x1", "y1", "x2", "y2", "track", "assocSimPct"],
                                  "lowConfidenceTracks": sorted(low), "rows": rs})


# --- pose
def yaw_deg(v):
    return float(np.degrees(np.arctan2(v[0], -v[2])))  # 0 = facing camera (-z), +90 = facing image right

for lab in "AB":
    p = VA / f"pose/pose-{lab}.npz"
    if not p.exists():
        continue
    z = np.load(p)
    k2, k3, s = z["k2"].astype(np.float32), z["k3"].astype(np.float32), z["s"].astype(np.float32)
    # torso orientation: normal of shoulder line x up vector in 3D crop space
    L, R = 5, 6
    sh = k3[:, R] - k3[:, L]
    sh[:, 1] = 0
    fwd = np.stack([-sh[:, 2], np.zeros(len(sh)), sh[:, 0]], 1)  # rotate shoulder vector 90deg about vertical
    torso = np.degrees(np.arctan2(fwd[:, 0], -fwd[:, 2]))
    # head orientation: nose relative to ear midpoint in 3D (estimate, NOT gaze)
    ears = (k3[:, 3] + k3[:, 4]) / 2
    hv = k3[:, 0] - ears
    head = np.degrees(np.arctan2(hv[:, 0], -hv[:, 2]))
    head_ok = (s[:, 0] > 0.3) & (np.maximum(s[:, 3], s[:, 4]) > 0.3)
    torso_ok = (s[:, 5] > 0.3) & (s[:, 6] > 0.3)
    root = (k3[:, 11] + k3[:, 12]) / 2
    by = collections.defaultdict(list)
    for i in range(len(z["t"])):
        by[int(z["rec"][i])].append(i)
    for rec, idx in by.items():
        f = W / f"pose-rec{rec:02d}.json"
        obj = json.loads(f.read_text()) if f.exists() else {"rec": rec, "keypointIndices": KP, "body3dIndices": list(range(23)),
                                                              "notes": "RTMW3D estimates. headYaw = head orientation estimate, not gaze. null = low confidence."}
        obj[lab] = {
            "frame": [int(z["frame"][i]) for i in idx],
            "k2": [[int(round(v * 10000)) for v in k2[i, KP].ravel()] for i in idx],
            "s": [[int(min(9, max(0, v * 10))) for v in s[i, KP]] for i in idx],
            "k3": [[int(round(v * 1000)) for v in (k3[i, :23] - root[i]).ravel()] for i in idx],
            "headYaw": [round(float(head[i])) if head_ok[i] else None for i in idx],
            "torsoYaw": [round(float(torso[i])) if torso_ok[i] else None for i in idx],
        }
        f.write_text(json.dumps(obj, separators=(",", ":")))

# --- material
for p in sorted((VA / "sam3").glob("sam3-rec*.jsonl.gz")):
    rec = int(p.name[8:10]); out = {"rec": rec, "fps": 1, "prompts": ["garment", "person"], "notes": "person masks omitted for size (A/B boxes cover people); polygons thinned to <=36 points; garment = surface/loose material; garmentOnPerson = garment masks >=60% inside a person mask (worn or held)", "frames": []}
    try:
        for l in gzip.open(p, "rt"):
            d = json.loads(l)
            surf, onp = split(d)
            def thin(pg, k=36):
                n = len(pg) // 2; st = max(1, -(-n // k))
                return [round(v * 10000) for i in range(0, n, st) for v in pg[2 * i:2 * i + 2]]
            enc = lambda ms: [{"s": round(m["s"] * 100), "poly": [thin(pg) for pg in m["poly"] if len(pg) >= 6]} for m in ms]
            out["frames"].append({"frame": d["frame"], "garment": enc(surf), "garmentOnPerson": enc(onp),
                                  "person": []})
    except EOFError:
        pass  # file still being written
    dump(f"material-rec{rec:02d}.json", out)
print(sorted(x.name for x in W.iterdir()))
