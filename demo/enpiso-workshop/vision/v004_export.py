#!/usr/bin/env python3
"""Export v0.0.4 product-3D web assets to media/vision-analysis/web/v004/."""
import sys, json, shutil, numpy as np, trimesh, cv2
from scipy.spatial import cKDTree
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from v002_common import *
SRC = VA / "v004"; OUT = VA / "web/v004"; OUT.mkdir(parents=True, exist_ok=True)

def decimate_colored(src, dst, faces=30000):
    m = trimesh.load(src, force="mesh"); col = m.visual.vertex_colors if m.visual.kind == "vertex" else m.visual.to_color().vertex_colors
    m = max(m.split(only_watertight=False), key=lambda p: len(p.faces)) if len(m.split(only_watertight=False)) > 1 else m
    d = m.simplify_quadric_decimation(face_count=faces)
    _, idx = cKDTree(trimesh.load(src, force="mesh").vertices).query(d.vertices)
    d.visual = trimesh.visual.ColorVisuals(d, vertex_colors=col[idx])
    d.vertices -= d.bounds.mean(0)
    d.export(dst); return len(d.faces), np.ptp(d.vertices, 0).round(3).tolist()

out = {}
# 1) CP-image model with projected print (already 40k faces, textured)
m = trimesh.load(SRC / "product/tee-sam3d-textured.glb", force="mesh")
tex = m.visual.material.baseColorTexture
m.visual.material.baseColorTexture = tex.convert("RGB").resize((tex.width // 2 * 2, tex.height // 2 * 2))
m.export(OUT / "tee-cp-sam3d.glb"); out["cp"] = dict(file="tee-cp-sam3d.glb", faces=len(m.faces), size_m=np.ptp(m.vertices, 0).round(3).tolist())
# 2) video reconstructions (vertex colors from the frame)
for t in ("t00448", "t04189"):
    f, s = decimate_colored(SRC / f"video/sam3d-{t}.glb", OUT / f"tee-video-{t}.glb")
    out[t] = dict(file=f"tee-video-{t}.glb", faces=f, size_units=s)
    shutil.copy2(SRC / f"video/{t}-check.jpg", OUT / f"tee-video-{t}-frame.jpg")
# 3) print texture for the procedural three.js tee + clean reference image
img = cv2.imread(str(SRC / "product/tee-clean.png")); mask = cv2.imread(str(SRC / "product/tee-mask.png"), 0) > 0
ys, xs = np.where(mask); crop = img[ys.min():ys.max() + 1, xs.min():xs.max() + 1].copy(); cm = mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
h, w = crop.shape[:2]; band = crop[int(.08 * h):int(.48 * h), int(.18 * w):int(.82 * w)]
g = cv2.cvtColor(band, cv2.COLOR_BGR2GRAY); a = np.clip((235 - g.astype(int)) * 3, 0, 255).astype(np.uint8)
rgba = np.dstack([band, a]); cv2.imwrite(str(OUT / "tee-print.png"), rgba)
ref = crop.copy(); ref[~cm] = 255; cv2.imwrite(str(OUT / "tee-cp-reference.png"), ref)
shutil.copy2(SRC / "product/tee-sam3d-textured-preview.png", OUT / "tee-cp-sam3d-preview.png")
prod = dict(
    product=dict(code="[PRODUCT]", description="[PRODUCT]", sam_total_min=3.8, cost=0, status="Activo",
                 processes=[dict(name="Preparacionpunto", sam=0.0, operations=["OPER000008 PREPMANGAELASTANO"]),
                            dict(name="Confeccion", sam=3.8, operations=["1 operation (Confección)"]),
                            dict(name="Empaque", sam=0.0, operations=["1 operation"])],
                 colors=[], size_ranges=[], category=None, images_in_cp=2),
    workOrder=dict(number=None, client=None, issued="2026-10-27", due="2026-10-27", size_on_video="L", size_before_11_22="XL", package=None),
    models=out,
    sources=[
        "CP product image (151×117 px, '[BRAND] · [PRINT] · ESTD 1985'), red callouts removed, upscaled ×6 (detail invented by interpolation).",
        "Shape A: SAM 3D Objects from the CP image; print projected on the front, chest print removed on the back (back is NOT observed).",
        "Shape B: SAM 3D Objects from single video frames (t=448 s held by B, t=4189 s lying in the queue); partial, single view.",
        "Procedural tee: generic short-sleeve crew-neck mesh built in three.js with the CP print as a decal; size L proportions are generic, not measured.",
        "Hunyuan3D-2mini was also tried on the CP image; output contained a large spurious sheet and was discarded.",
    ],
    caveats=["Estimated 3D, not measured geometry.", "No CP technical sheet (measurements, seams, fabric) exists; only SAM and process list.",
             "'[PRINT]' is likely a client trademark; shown for this semi-private POC only."],
)
json.dump(prod, open(OUT / "product.json", "w"), indent=1, ensure_ascii=False)
print(json.dumps(out, indent=1)); import os; print({f: os.path.getsize(OUT / f) // 1024 for f in os.listdir(OUT)})
