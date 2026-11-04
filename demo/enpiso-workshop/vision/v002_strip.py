#!/usr/bin/env python3
"""Dense validation strips around a timeline instant: v002_strip.py T0 START END STEP OUT [crop x0,y0,x1,y1]."""
import sys
import cv2, numpy as np
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from v002_common import *

t0, a, b, step = (float(v) for v in sys.argv[1:5]); out = sys.argv[5]
crop = [int(v) for v in sys.argv[6].split(",")] if len(sys.argv) > 6 else [0, 180, 1440, 810]
P = {lab: load_pose(lab) for lab in "AB"}
COL = {"A": (255, 0, 255), "B": (0, 200, 255)}
import os
TW = int(os.environ.get("TW", 640)); COLS = int(os.environ.get("COLS", 3))
fr = Frames(); tiles = []
ZONES = {}
try:
    ZONES = json.load(open(POC / "zones.json"))
except Exception:
    pass
for o in np.arange(a, b + 1e-6, step):
    t = t0 + o; img = fr.get(t)
    for lab in "AB":
        z = P[lab]; j = np.argmin(np.abs(z["t"] - t))
        if abs(z["t"][j] - t) < 0.25:
            bx = z["box"][j]
            cv2.rectangle(img, (int(bx[0]*W), int(bx[1]*H)), (int(bx[2]*W), int(bx[3]*H)), COL[lab], 2)
            for (x, y), sc in zip(z["k2"][j][HAND].astype(float), z["s"][j][HAND].astype(float)):
                if sc >= 0.3: cv2.circle(img, (int(x*W), int(y*H)), 3, COL[lab], -1)
    for name, poly in ZONES.get("zones", {}).items():
        pts = (np.array(poly).reshape(-1, 2) * [W, H]).astype(np.int32)
        cv2.polylines(img, [pts], True, (0, 255, 0), 2)
    tile = img[crop[1]:crop[3], crop[0]:crop[2]]
    sc = TW / tile.shape[1]; tile = cv2.resize(tile, (TW, int(tile.shape[0]*sc)))
    cv2.rectangle(tile, (0, 0), (190, 22), (0, 0, 0), -1)
    cv2.putText(tile, f"{o:+.0f}s  {hms(tl_to_cam(t))}", (4, 16), 0, 0.5, (255, 255, 255), 1)
    tiles.append(tile)
cols = COLS
while len(tiles) % cols: tiles.append(np.zeros_like(tiles[0]))
cv2.imwrite(out, np.vstack([np.hstack(tiles[i:i+cols]) for i in range(0, len(tiles), cols)]), [cv2.IMWRITE_JPEG_QUALITY, 80])
print(out)
