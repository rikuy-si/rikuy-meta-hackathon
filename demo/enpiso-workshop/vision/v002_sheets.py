#!/usr/bin/env python3
"""Cycle sheets: one JPG per detected cycle, from A's supply (piece enters the queue) to B's deposit
(B turns toward the camera and lowers the piece out of frame). Also an index sheet.
Writes media/vision-analysis/v002/sheets/cycle-NN.jpg, index.jpg, sheets.json."""
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from v002_common import *
import cv2

OUT = V2 / "sheets"; OUT.mkdir(exist_ok=True)
C = json.load(open(VA / "analysis/v002-cycles.json"))
Z = json.load(open(POC / "zones.json"))["zones"]
P = {l: load_pose(l) for l in "AB"}
COL = {"A": (255, 0, 255), "B": (0, 200, 255)}
ZC = {"queue": (80, 220, 80), "keypad": (0, 140, 255), "b_station": (200, 200, 200), "a_seat": (180, 120, 255)}
CROP = (180, 300, 1440, 810)  # x0,y0,x1,y1: A's table, queue, keypad, B station, bottom exit edge
TW = 420
fr = Frames()


def tile(t, label):
    img = fr.get(max(0.0, t))
    for name, poly in Z.items():
        if name in ("b_station", "a_seat"): continue
        pts = (np.array(poly).reshape(-1, 2) * [W, H]).astype(np.int32)
        cv2.polylines(img, [pts], True, ZC[name], 2)
    for l in "AB":
        z = P[l]; j = np.argmin(np.abs(z["t"] - t))
        if abs(z["t"][j] - t) < 0.3:
            b = z["box"][j]
            cv2.rectangle(img, (int(b[0]*W), int(b[1]*H)), (int(b[2]*W), int(b[3]*H)), COL[l], 2)
            cv2.putText(img, l, (int(b[0]*W) + 4, int(b[1]*H) + 24), 0, 0.9, COL[l], 2)
            for (x, y), sc in zip(z["k2"][j][HAND].astype(float), z["s"][j][HAND].astype(float)):
                if sc >= 0.3: cv2.circle(img, (int(x*W), int(y*H)), 3, COL[l], -1)
    im = img[CROP[1]:CROP[3], CROP[0]:CROP[2]]
    im = cv2.resize(im, (TW, int(im.shape[0] * TW / im.shape[1])))
    cv2.rectangle(im, (0, 0), (TW, 34), (0, 0, 0), -1)
    cv2.putText(im, label, (4, 14), 0, 0.45, (255, 255, 255), 1)
    cv2.putText(im, f"t={t:.0f}s cam {hms(tl_to_cam(t))}", (4, 29), 0, 0.42, (200, 200, 200), 1)
    return im


meta = []
thumbs = []
for c in C["cycles"]:
    n = c["n"]; hs, he, dep = c["handoff_start"], c["handoff_end"], c["b_deposit"]
    ts = []
    if c["a_place"] is not None and c["a_place"] < hs - 2:
        ts.append((c["a_place"], "1 A supplies piece (queue)"))
    else:
        ts.append((hs - 6, "1 before pick-up (A supply not seen)"))
    ts.append((hs, "2 B arrives at A's table"))
    ts.append((he, "3 B back at overlock"))
    end = dep if dep is not None else (c["next_handoff"] - 3 if c["next_handoff"] else he + 60)
    ts.append(((he + end) / 2, "4 B working (mid)"))
    ts.append((end - 3, "5 just before deposit" if dep is not None else "5 (deposit not detected)"))
    ts.append((end, "6 B turns to camera / deposit" if dep is not None else "6 next pick-up approaching"))
    ts.append((end + 3, "7 piece leaves frame (inferred)" if dep is not None else "7 -"))
    tiles = [tile(t, f"C{n:02d} {lab}") for t, lab in ts]
    while len(tiles) % 4: tiles.append(np.zeros_like(tiles[0]))
    sheet = np.vstack([np.hstack(tiles[i:i+4]) for i in range(0, len(tiles), 4)])
    hdr = np.zeros((40, sheet.shape[1], 3), np.uint8)
    txt = (f"Cycle C{n:02d} [{c['handoff']}]  queue dwell {c['queue_dwell']}s  B wait {c['b_wait']}s  "
           f"B work {c['b_work']}s  B cycle {c['b_cycle']}s  flags {','.join(c['flags']) or '-'}")
    cv2.putText(hdr, txt, (8, 26), 0, 0.6, (255, 255, 255), 1)
    sheet = np.vstack([hdr, sheet])
    fn = f"cycle-{n:02d}.jpg"
    cv2.imwrite(str(OUT / fn), sheet, [cv2.IMWRITE_JPEG_QUALITY, 80])
    meta.append(dict(n=n, file=fn, frames=[dict(t=round(t, 1), label=lab) for t, lab in ts]))
    th = cv2.resize(tiles[5] if dep is not None else tiles[1], (210, int(tiles[1].shape[0] * 210 / TW)))
    cv2.putText(th, f"C{n:02d}", (4, 50), 0, 0.6, (0, 255, 255), 2)
    thumbs.append(th)
    print(fn, flush=True)
while len(thumbs) % 8: thumbs.append(np.zeros_like(thumbs[0]))
cv2.imwrite(str(OUT / "index.jpg"), np.vstack([np.hstack(thumbs[i:i+8]) for i in range(0, len(thumbs), 8)]), [cv2.IMWRITE_JPEG_QUALITY, 80])
json.dump(meta, open(OUT / "sheets.json", "w"), indent=1)
print("ok", len(meta))
