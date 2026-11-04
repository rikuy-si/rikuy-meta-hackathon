#!/usr/bin/env python3
"""QA sheet: for N excursions of a person, frames at start, farthest point, end (downscaled full frame with box)."""
import json, sys, gzip
from pathlib import Path
import av, numpy as np, cv2

ROOT = Path(__file__).resolve().parents[1]
VR = ROOT / "enpiso/video-review"; VA = VR / "media/vision-analysis"
pl = json.load(open(VR / "full-playlist.json")); R = pl["recordings"]
lab = sys.argv[1]; n = int(sys.argv[2]) if len(sys.argv) > 2 else 12
ex = json.load(open(VA / "analysis/excursions.json"))[lab]["episodes"]
ex = sorted(ex, key=lambda e: -e["duration_s"])[:n]
ex.sort(key=lambda e: e["t0"])
boxes = {}
for l in gzip.open(VA / "ab/ab-detections.jsonl.gz", "rt"):
    d = json.loads(l)
    if d["label"] == lab:
        boxes[round(d["t"], 1)] = d["box"]


def grab(t):
    i = max(j for j, r in enumerate(R) if r["timelineStart"] <= t)
    c = av.open(str(VR / "media/full-playlist-v1" / R[i]["file"])); s = c.streams.video[0]
    off = t - R[i]["timelineStart"]; c.seek(int(max(0, off - 2) / s.time_base), stream=s)
    for fr in c.decode(s):
        if float(fr.pts * s.time_base) >= off - 0.04:
            img = fr.to_ndarray(format="bgr24"); break
    c.close()
    b = boxes.get(round(t, 1))
    if b:
        cv2.rectangle(img, (int(b[0] * 1440), int(b[1] * 810)), (int(b[2] * 1440), int(b[3] * 810)), (0, 0, 255), 4)
    return cv2.resize(img, (480, 270))

rows = []
for e in ex:
    tiles = [grab(e["t0"]), grab(e["farthest_t"]), grab(e["t1"])]
    cv2.putText(tiles[0], f"{lab} {e['camera_start']} {e['duration_s']}s", (5, 20), 0, 0.6, (0, 255, 255), 2)
    rows.append(np.hstack(tiles))
cv2.imwrite(str(VA / f"analysis/qa-excursions-{lab}.jpg"), np.vstack(rows))
print(len(rows))
