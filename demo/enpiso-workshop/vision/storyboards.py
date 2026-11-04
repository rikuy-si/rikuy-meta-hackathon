#!/usr/bin/env python3
"""Per-candidate review storyboards (work area crop) with A/B boxes, hand keypoints, device zone.
Writes one JPG per candidate (for the app/report) and 4-candidate sheets for reviewer QA."""
import json
from pathlib import Path
import av, numpy as np, cv2

ROOT = Path(__file__).resolve().parents[1]
VR = ROOT / "enpiso/video-review"; VA = VR / "media/vision-analysis"; OUT = VA / "storyboards"; OUT.mkdir(exist_ok=True)
pl = json.load(open(VR / "full-playlist.json")); R = pl["recordings"]
OFFS = [-30, -15, -5, 0, 5, 15]
CROP = (230, 330, 1330, 810)
P = {lab: np.load(VA / f"pose/pose-{lab}.npz") for lab in "AB"}
HAND = [9, 10] + list(range(91, 133))
COL = {"A": (255, 0, 255), "B": (0, 200, 255)}
DEV = [0.555, 0.665, 0.610, 0.750]


def frame_at(t):
    i = max(j for j, r in enumerate(R) if r["timelineStart"] <= t)
    c = av.open(str(VR / "media/full-playlist-v1" / R[i]["file"])); s = c.streams.video[0]
    off = t - R[i]["timelineStart"]; c.seek(int(max(0, off - 2) / s.time_base), stream=s)
    img = None
    for fr in c.decode(s):
        if float(fr.pts * s.time_base) >= off - 0.04:
            img = fr.to_ndarray(format="bgr24"); break
    c.close(); return img

rows = []
for n, e in enumerate(pl["events"]):
    tiles = []
    for o in OFFS:
        t = e["timeline"] + o
        img = frame_at(t)
        for lab in "AB":
            z = P[lab]; j = np.argmin(np.abs(z["t"] - t))
            if abs(z["t"][j] - t) < 0.25:
                b = z["box"][j]
                cv2.rectangle(img, (int(b[0] * 1440), int(b[1] * 810)), (int(b[2] * 1440), int(b[3] * 810)), COL[lab], 2)
                cv2.putText(img, lab, (int(b[0] * 1440) + 4, int(b[1] * 810) + 22), 0, 0.8, COL[lab], 2)
                for (x, y), sc in zip(z["k2"][j][HAND].astype(float), z["s"][j][HAND].astype(float)):
                    if sc >= 0.3:
                        cv2.circle(img, (int(x * 1440), int(y * 810)), 2, COL[lab], -1)
        cv2.rectangle(img, (int(DEV[0] * 1440), int(DEV[1] * 810)), (int(DEV[2] * 1440), int(DEV[3] * 810)), (0, 255, 0), 2)
        tile = img[CROP[1]:CROP[3], CROP[0]:CROP[2]]
        tile = cv2.resize(tile, (440, 192))
        cv2.rectangle(tile, (0, 0), (150, 20), (0, 0, 0), -1)
        cv2.putText(tile, f"{e['id']} {o:+d}s", (4, 15), 0, 0.5, (255, 255, 255), 1)
        tiles.append(tile)
    row = np.hstack(tiles)
    cv2.imwrite(str(OUT / f"{e['id']}.jpg"), row, [cv2.IMWRITE_JPEG_QUALITY, 85])
    rows.append(row)
    if len(rows) == 4 or n == len(pl["events"]) - 1:
        cv2.imwrite(str(OUT / f"sheet-{n // 4 + 1:02d}.jpg"), np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 85]); rows = []
print("ok")
