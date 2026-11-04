#!/usr/bin/env python3
"""Static figures: (1) A/B position density + excursion endpoints on the scene; (2) process timeline."""
import json, gzip, collections
from pathlib import Path
import numpy as np, cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
VR = ROOT / "enpiso/video-review"; VA = VR / "media/vision-analysis"; FIG = VA / "figures"; FIG.mkdir(exist_ok=True)
pl = json.load(open(VR / "full-playlist.json")); EV = pl["events"]
scene = cv2.imread(str(VA / "3d/scene/scene-rec05-492s.png"))
H, W = scene.shape[:2]
pos = {"A": [], "B": []}; ts = {"A": [], "B": []}
for l in gzip.open(VA / "ab/ab-detections.jsonl.gz", "rt"):
    d = json.loads(l); b = d["box"]
    pos[d["label"]].append(((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)); ts[d["label"]].append(d["t"])
COL = {"A": (255, 0, 200), "B": (255, 200, 0)}
img = (scene * 0.55).astype(np.uint8)
for lab in "AB":
    hm = np.zeros((H, W), np.float32)
    for x, y in pos[lab]:
        cv2.circle(hm, (int(x * W), int(y * H)), 6, 1, -1)
    hm = cv2.GaussianBlur(hm, (0, 0), 12); hm /= hm.max()
    for c in range(3):
        img[..., c] = np.clip(img[..., c] + hm * COL[lab][c] * 0.9, 0, 255)
ex = json.load(open(VA / "analysis/excursions.json"))
for lab in "AB":
    h = ex[lab]["home_center"]
    for e in ex[lab]["episodes"]:
        f = e["farthest_center"]
        cv2.arrowedLine(img, (int(h[0] * W), int(h[1] * H)), (int(f[0] * W), int(f[1] * H)), COL[lab], 1, tipLength=0.03)
    cv2.circle(img, (int(h[0] * W), int(h[1] * H)), 10, COL[lab], 3)
    cv2.putText(img, f"{lab} home", (int(h[0] * W) + 12, int(h[1] * H)), 0, 0.8, COL[lab], 2)
Z = json.load(open(VA / "analysis/events-analysis.json"))["meta"]["zones"]
for k, z in Z.items():
    cv2.rectangle(img, (int(z[0] * W), int(z[1] * H)), (int(z[2] * W), int(z[3] * H)), (0, 255, 0) if k == "cp_device" else (200, 200, 200), 2 if k == "cp_device" else 1)
    cv2.putText(img, k, (int(z[0] * W) + 4, int(z[1] * H) + 16), 0, 0.5, (0, 255, 0) if k == "cp_device" else (230, 230, 230), 1)
cv2.putText(img, "A (magenta) / B (yellow): position density 14:09-15:49; arrows = home -> farthest point of each excursion >=3 s", (10, H - 12), 0, 0.55, (255, 255, 255), 1)
cv2.imwrite(str(FIG / "ab-position-map.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 88])

# timeline
tl = json.load(open(VA / "analysis/zone-timeline.json"))["bins"]
ZN = ["central_table", "b_station", "right_racks", "back_center_aisle", "back_left_tables", "front_left", "other"]
fig, ax = plt.subplots(4, 1, figsize=(16, 9), sharex=True, gridspec_kw={"height_ratios": [2, 2, 1.2, 1.6]})
def cam_min(t):  # minutes since 14:09:24 camera (window is contiguous for recs 1-8)
    return t / 60
for i, lab in enumerate("AB"):
    xs = [cam_min(r["t"]) for r in tl if lab in r]; ys = [ZN.index(r[lab]) if r[lab] in ZN else len(ZN) - 1 for r in tl if lab in r]
    ax[i].scatter(xs, ys, s=3, c="m" if lab == "A" else "orange")
    ax[i].set_yticks(range(len(ZN))); ax[i].set_yticklabels(ZN, fontsize=7); ax[i].set_ylabel(lab)
    dv = [cam_min(r["t"]) for r in tl if r.get(lab + "dev")]
    ax[i].scatter(dv, [-0.8] * len(dv), marker="|", s=40, c="g", label="hand keypoints in CP-device zone")
    ax[i].legend(loc="upper right", fontsize=7)
for e in EV:
    for a in ax:
        a.axvline(cam_min(e["timeline"]), color="r", lw=0.6, alpha=0.6)
ax[2].set_ylabel("CP\ncandidates"); ax[2].set_yticks([])
for e in EV:
    ax[2].text(cam_min(e["timeline"]), 0.5, e["id"], rotation=90, fontsize=6, ha="center", va="center")
g = collections.defaultdict(list)
for r in tl:
    for k in ("central_table", "b_station", "cp_device", "right_racks"):
        g[k].append(r["garment"].get(k, 0) * 100)
xs = [cam_min(r["t"]) for r in tl]
for k, v in g.items():
    sm = np.convolve(v, np.ones(6) / 6, mode="same")
    ax[3].plot(xs, sm, lw=1, label=k)
ax[3].set_ylabel("SAM3 'garment'\n% frame area"); ax[3].legend(fontsize=7, ncol=4)
ax[3].set_xlabel("minutes since camera 14:09:24 (red lines = CP candidates mapped with +3603 s, ±5 s)")
fig.suptitle("Workshop 2026-10-30 — anonymous A/B zone timeline, CP-device hand proximity, and garment area (video estimates)")
plt.tight_layout(); plt.savefig(FIG / "process-timeline.png", dpi=110)
print("ok")
