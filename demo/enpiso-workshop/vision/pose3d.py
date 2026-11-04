#!/usr/bin/env python3
"""RTMW3D whole-body (133 kpts) 3D pose for assigned A/B detections at 5 fps, streamed.

Input: vision-analysis/ab/ab-detections.jsonl.gz (rec, frame, label, box normalized).
Output: vision-analysis/pose/pose-<label>.npz with per-sample 2D image keypoints (normalized),
crop-space 3D keypoints (x,y crop px / input size, z relative), scores, and derived
torso/head yaw estimates. Head yaw = head orientation estimate, NOT gaze.
"""
import gzip, json, os, collections, time
from pathlib import Path
import av, numpy as np
import onnxruntime as ort
ort.preload_dlls()
from rtmlib import RTMPose3d

ROOT = Path(__file__).resolve().parents[1]
VR = ROOT / "enpiso/video-review"
VA = VR / "media/vision-analysis"
OUT = VA / "pose"; OUT.mkdir(parents=True, exist_ok=True)
ONNX = os.path.expanduser("~/.cache/rtmlib/hub/checkpoints/rtmw3d-x_8xb64_cocktail14-384x288-b0a0eab7_20240626.onnx")

want = collections.defaultdict(list)
for l in gzip.open(VA / "ab/ab-detections.jsonl.gz", "rt"):
    d = json.loads(l)
    want[(d["rec"], d["frame"])].append((d["label"], d["box"]))

m = RTMPose3d(ONNX, device="cuda")
res = {"A": collections.defaultdict(list), "B": collections.defaultdict(list)}
pl = json.load(open(VR / "full-playlist.json"))
t0 = time.time(); n = 0
for r in pl["recordings"]:
    frames = {fr for (rec, fr) in want if rec == r["id"]}
    if not frames:
        continue
    last = max(frames)
    c = av.open(str(VR / "media/full-playlist-v1" / r["file"])); s = c.streams.video[0]; s.thread_type = "AUTO"
    for fr in c.decode(s):
        idx = round(float(fr.pts * s.time_base) * 15)
        if idx > last:
            break
        if idx not in frames:
            continue
        img = fr.to_ndarray(format="rgb24"); H, W = img.shape[:2]
        items = want[(r["id"], idx)]
        bbs = [[b[0] * W, b[1] * H, b[2] * W, b[3] * H] for _, b in items]
        k3, sc, _, k2 = m(img, bboxes=bbs)
        for (lab, b), a3, s_, a2 in zip(items, k3, sc, k2):
            R = res[lab]
            R["rec"].append(r["id"]); R["frame"].append(idx); R["t"].append(r["timelineStart"] + idx / 15)
            R["box"].append(b)
            R["k2"].append((a2 / [W, H]).astype(np.float16))
            R["k3"].append(np.c_[a3[:, 0] / 288, a3[:, 1] / 384, a3[:, 2]].astype(np.float16))
            R["s"].append(s_.astype(np.float16))
            n += 1
    c.close()
    print(json.dumps({"rec": r["id"], "samples": n, "elapsed_s": round(time.time() - t0, 1)}), flush=True)

for lab, R in res.items():
    if R["t"]:
        np.savez_compressed(OUT / f"pose-{lab}.npz", **{k: np.array(v) for k, v in R.items()})
print("done", n)
