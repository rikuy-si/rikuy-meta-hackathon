#!/usr/bin/env python3
"""QA contact sheets: one crop per assigned/uncertain tracklet (middle sample), labelled with track id and time."""
import gzip, json, collections, sys
from pathlib import Path
import av, numpy as np, cv2

ROOT = Path(__file__).resolve().parents[1]
VR = ROOT / "enpiso/video-review"; VA = VR / "media/vision-analysis"
A = json.load(open(VA / "ab/ab-assignment.json"))
mode = sys.argv[1] if len(sys.argv) > 1 else "assigned"
items = A[mode]
# middle sample per tracklet from track files
need = {}
import glob
mid = {int(k): (v["t0"] + v["t1"]) / 2 for k, v in items.items()}
for f in sorted(glob.glob(str(VA / "tracks/full5-rec*.jsonl.gz"))):
    for l in gzip.open(f, "rt"):
        d = json.loads(l)
        for p in d["p"]:
            if p[0] in mid and (p[0] not in need or abs(d["t"] - mid[p[0]]) < abs(need[p[0]][2] - mid[p[0]])):
                need[p[0]] = (d["rec"], d["frame"], d["t"], p[1:5])
want = collections.defaultdict(list)
for tid, (rec, fr, t, b) in need.items():
    want[(rec, fr)].append((tid, t, b))
pl = json.load(open(VR / "full-playlist.json"))
crops = {}
for r in pl["recordings"]:
    fs = {fr for (rec, fr) in want if rec == r["id"]}
    if not fs:
        continue
    c = av.open(str(VR / "media/full-playlist-v1" / r["file"])); s = c.streams.video[0]; s.thread_type = "AUTO"
    for frm in c.decode(s):
        idx = round(float(frm.pts * s.time_base) * 15)
        if idx > max(fs):
            break
        if idx in fs:
            img = frm.to_ndarray(format="bgr24"); H, W = img.shape[:2]
            for tid, t, b in want[(r["id"], idx)]:
                cr = img[int(b[1] * H):int(b[3] * H), int(b[0] * W):int(b[2] * W)]
                cr = cv2.resize(cr, (120, 200))
                lab = items[str(tid)].get("label") or items[str(tid)].get("label_guess")
                cv2.rectangle(cr, (0, 0), (119, 30), (0, 0, 0), -1)
                cv2.putText(cr, f"{lab}{tid} {int(t)//60}m", (2, 13), 0, 0.4, (255, 255, 255), 1)
                cv2.putText(cr, f"{items[str(tid)]['sim']:.2f} n{items[str(tid)]['n']}", (2, 27), 0, 0.4, (0, 255, 255), 1)
                crops[(lab, t, tid)] = cr
    c.close()
for lab in "AB":
    cs = [v for k, v in sorted(crops.items()) if k[0] == lab]
    if not cs:
        continue
    cols = 14; rows = (len(cs) + cols - 1) // cols
    sheet = np.zeros((rows * 200, cols * 120, 3), np.uint8)
    for i, cimg in enumerate(cs):
        sheet[(i // cols) * 200:(i // cols + 1) * 200, (i % cols) * 120:(i % cols + 1) * 120] = cimg
    cv2.imwrite(str(VA / f"ab/qa-{mode}-{lab}.jpg"), sheet)
    print(lab, len(cs))
