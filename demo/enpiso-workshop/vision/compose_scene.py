#!/usr/bin/env python3
"""Compose SAM 3D Objects single-image reconstructions into one camera-frame scene GLB.

v_local = v_glb @ M.T  (to_glb applied v @ M, M=[[1,0,0],[0,0,-1],[0,1,0]])
p_cam   = (s * v_local) @ R(q) + t   (PyTorch3D row-vector Transform3d: scale -> rotate -> translate)
PyTorch3D camera: +X left, +Y up, +Z forward. Output (three.js): x=-X, y=Y, z=-Z (camera at origin looking -z).
Validation: reproject composed vertices with a pinhole whose focal length is fit by least squares to the
SAM 3 mask centroids; report per-object centroid error in pixels."""
import json, sys
from pathlib import Path
import numpy as np, trimesh, cv2

D = Path(__file__).resolve().parents[1] / "enpiso/video-review/media/vision-analysis/3d/scene"
M = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]], float)
LABELS = {"sewing_machine_7": "JACK lockstitch machine (central table)", "sewing_machine_2": "JACK overlock (B station)",
          "sign_board_2": "FÉNIX team sign", "pile_of_clothes_0": "brown garment pile (racks)", "table_5": "central work table (A)",
          "table_2": "B station table", "sewing_machine_5": "back-left sewing machine", "table_8": "left work table"}


def qmat(q):
    w, x, y, z = q / np.linalg.norm(q)
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])

img = cv2.imread(str(D / "scene-rec05-492s.png")); H, W = img.shape[:2]
scene = trimesh.Scene(); objs = []; man = []
for k, label in LABELS.items():
    js, glb = D / f"obj-{k}.json", D / f"obj-{k}.glb"
    if not glb.exists():
        continue
    info = json.load(open(js)); p = info["pose"]
    q = np.array(p["rotation"][0]); t = np.array(p["translation"][0]); s = np.array(p["scale"][0])
    g = trimesh.load(glb, force="mesh")
    v_local = g.vertices @ M.T
    R = qmat(q)  # pytorch3d quaternion_to_matrix gives column-vector matrix; Transform3d.rotate(R) uses p @ R
    pc = (v_local * s) @ R + t
    out = pc * np.array([-1, 1, -1])
    m = g.copy(); m.vertices = out
    scene.add_geometry(m, node_name=k, geom_name=k)
    mask = cv2.imread(str(D / f"mask-{k}.png"), 0) > 0
    ys, xs = np.nonzero(mask)
    objs.append((k, pc, (xs.mean(), ys.mean())))
    man.append({"id": k, "label": label, "glb": f"obj-{k}.glb", "maskPixels": int(mask.sum()),
                "pose": p, "inference_s": info.get("inference_s")})

# fit focal for reprojection check: u = cx + f * (-X/Z)?  try both sign conventions, keep the better.
best = None
for sx in (-1, 1):
    A, b = [], []
    for k, pc, (mx, my) in objs:
        c = pc.mean(0); A += [[sx * c[0] / c[2]], [-c[1] / c[2]]]; b += [mx - W / 2, my - H / 2]
    f, res, *_ = np.linalg.lstsq(np.array(A), np.array(b), rcond=None)
    err = [float(np.hypot(W / 2 + f[0] * sx * pc.mean(0)[0] / pc.mean(0)[2] - mx, H / 2 - f[0] * pc.mean(0)[1] / pc.mean(0)[2] - my)) for k, pc, (mx, my) in objs]
    if best is None or np.median(err) < np.median(best[2]):
        best = (sx, float(f[0]), err)
sx, f, err = best
vis = img.copy()
for (k, pc, (mx, my)), e in zip(objs, err):
    sel = pc[np.random.default_rng(0).choice(len(pc), min(3000, len(pc)), replace=False)]
    u = W / 2 + f * sx * sel[:, 0] / sel[:, 2]; v = H / 2 - f * sel[:, 1] / sel[:, 2]
    col = tuple(int(c) for c in np.random.default_rng(hash(k) % 2**32).integers(80, 255, 3))
    for a, b_ in zip(u.astype(int), v.astype(int)):
        if 0 <= a < W and 0 <= b_ < H:
            vis[b_, a] = col
    cv2.putText(vis, f"{k} err {e:.0f}px", (int(mx), int(my)), 0, 0.45, col, 1)
cv2.imwrite(str(D / "scene-reprojection-check.jpg"), vis)
scene.export(D / "scene-composed.glb")
for m_, e in zip(man, err):
    m_["reprojectionCentroidErrorPx"] = round(e, 1)
manifest = {"sourceFrame": {"recording": 5, "file": "module-full-05.mp4", "seconds": 492, "camera": "15:25:54"},
            "composed": {"glb": "scene-composed.glb", "frame": "camera at origin looking -z, +y up (three.js); units = SAM 3D metric-ish estimate",
                         "fitFocalPx": round(f, 1), "xSign": sx, "medianCentroidErrorPx": round(float(np.median(err)), 1)},
            "objects": man,
            "notes": "SAM 3D Objects single-image estimates (one frame). Hidden surfaces are hallucinated; scale/pose approximate. Not observed geometry."}
json.dump(manifest, open(D / "manifest.json", "w"), indent=1)
print("focal", round(f, 1), "xsign", sx, "errors", [round(e) for e in err])
