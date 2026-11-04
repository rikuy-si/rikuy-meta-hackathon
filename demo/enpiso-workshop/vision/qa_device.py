#!/usr/bin/env python3
"""QA strips: device-area crops around candidates with A/B hand keypoints drawn (A=magenta, B=cyan)."""
import json, sys
from pathlib import Path
import av, numpy as np, cv2

ROOT = Path(__file__).resolve().parents[1]
VR = ROOT / "enpiso/video-review"; VA = VR / "media/vision-analysis"
pl = json.load(open(VR / "full-playlist.json")); R = pl["recordings"]
ids = sys.argv[1].split(","); offs = [float(x) for x in sys.argv[2].split(",")] if len(sys.argv) > 2 else [-8, -4, -2, 0, 2, 4, 8]
CROP = (700, 430, 1020, 730)
P = {lab: np.load(VA / f"pose/pose-{lab}.npz") for lab in "AB"}
HAND = [9, 10] + list(range(91, 133))
rows = []
for cid in ids:
    e = next(x for x in pl["events"] if x["id"] == cid)
    tiles = []
    for o in offs:
        t = e["timeline"] + o
        i = max(j for j, r in enumerate(R) if r["timelineStart"] <= t)
        c = av.open(str(VR / "media/full-playlist-v1" / R[i]["file"])); s = c.streams.video[0]
        off = t - R[i]["timelineStart"]; c.seek(int(max(0, off - 2) / s.time_base), stream=s)
        img = None
        for fr in c.decode(s):
            if float(fr.pts * s.time_base) >= off - 0.04:
                img = fr.to_ndarray(format="bgr24"); break
        c.close()
        for lab, col in (("A", (255, 0, 255)), ("B", (255, 255, 0))):
            z = P[lab]; j = np.argmin(np.abs(z["t"] - t))
            if abs(z["t"][j] - t) < 0.25:
                for (x, y), sc in zip(z["k2"][j][HAND].astype(float), z["s"][j][HAND].astype(float)):
                    if sc >= 0.3:
                        cv2.circle(img, (int(x * 1440), int(y * 810)), 3, col, -1)
        cv2.rectangle(img, (int(0.555 * 1440), int(0.665 * 810)), (int(0.61 * 1440), int(0.75 * 810)), (0, 255, 0), 1)
        tile = img[CROP[1]:CROP[3], CROP[0]:CROP[2]].copy()
        cv2.putText(tile, f"{cid} {o:+.0f}s", (5, 20), 0, 0.6, (0, 0, 255), 2)
        tiles.append(tile)
    rows.append(np.hstack(tiles))
cv2.imwrite(str(VA / f"analysis/qa-device-{'-'.join(ids)}.jpg"), np.vstack(rows))
print("ok")
