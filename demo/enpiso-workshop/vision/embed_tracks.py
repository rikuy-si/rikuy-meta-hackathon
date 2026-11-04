#!/usr/bin/env python3
"""Second streaming pass at 1 fps: DINOv2-small appearance embeddings of every tracked person crop.
Writes per-track mean embedding + per-sample embeddings (npz) for A/B association. No raw frames stored."""
import gzip, json, glob, collections
from pathlib import Path
import av, numpy as np, torch
from transformers import AutoImageProcessor, AutoModel

ROOT = Path(__file__).resolve().parents[1]
VR = ROOT / "enpiso/video-review"
TR = VR / "media/vision-analysis/tracks"
OUT = VR / "media/vision-analysis/reid"; OUT.mkdir(parents=True, exist_ok=True)

boxes = collections.defaultdict(dict)  # (rec, frame) -> {tid: box}
for f in sorted(glob.glob(str(TR / "full5-rec*.jsonl.gz"))):
    for l in gzip.open(f, "rt"):
        d = json.loads(l)
        if d["frame"] % 15:
            continue
        for p in d["p"]:
            if p[0] >= 0 and (p[4] - p[2]) > 0.12:
                boxes[(d["rec"], d["frame"])][p[0]] = p[1:5]

proc = AutoImageProcessor.from_pretrained("facebook/dinov2-small")
model = AutoModel.from_pretrained("facebook/dinov2-small").cuda().half().eval()
pl = json.load(open(VR / "full-playlist.json"))
keys, embs = [], []
for r in pl["recordings"]:
    if r["id"] > 8:
        continue
    want = {fr for (rec, fr) in boxes if rec == r["id"]}
    if not want:
        continue
    c = av.open(str(VR / "media/full-playlist-v1" / r["file"])); s = c.streams.video[0]; s.thread_type = "AUTO"
    for fr in c.decode(s):
        idx = round(float(fr.pts * s.time_base) * 15)
        if idx not in want:
            continue
        img = fr.to_ndarray(format="rgb24"); H, W = img.shape[:2]
        crops, ids = [], []
        for tid, (x1, y1, x2, y2) in boxes[(r["id"], idx)].items():
            cr = img[int(y1 * H):int(y2 * H), int(x1 * W):int(x2 * W)]
            if cr.size == 0:
                continue
            crops.append(cr); ids.append(tid)
        if not crops:
            continue
        with torch.no_grad():
            x = proc(images=crops, return_tensors="pt")["pixel_values"].cuda().half()
            o = model(pixel_values=x)
            e = torch.cat([o.last_hidden_state[:, 0], o.last_hidden_state[:, 1:].mean(1)], 1)
            e = torch.nn.functional.normalize(e.float(), dim=1).cpu().numpy()
        for tid, v in zip(ids, e):
            keys.append((r["id"], idx, tid)); embs.append(v)
    c.close(); print("rec", r["id"], len(keys), flush=True)
np.savez_compressed(OUT / "track-embeddings.npz", keys=np.array(keys), embs=np.array(embs, dtype=np.float16))
print("done", len(keys))
