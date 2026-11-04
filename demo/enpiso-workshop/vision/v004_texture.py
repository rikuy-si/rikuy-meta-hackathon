#!/usr/bin/env python3
"""Clean + texture a garment GLB with the CP print by planar front projection.
v004_texture.py IN.glb OUT.glb [--flip]  -> keeps the largest component, recenters, scales to 0.72 m wide (adult L tee chest+sleeves, approx.),
UV = front-plane projection onto an atlas: left half = front (print), right half = back (print removed)."""
import sys, numpy as np, trimesh, cv2, pathlib
from PIL import Image
src, out = sys.argv[1], sys.argv[2]; flip = "--flip" in sys.argv
P = pathlib.Path(__file__).resolve().parents[1] / "enpiso/video-review/media/vision-analysis/v004/product"
img = cv2.imread(str(P / "tee-clean.png")); mask = cv2.imread(str(P / "tee-mask.png"), 0) > 0
ys, xs = np.where(mask); x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
front = img[y0:y1 + 1, x0:x1 + 1].copy(); m = mask[y0:y1 + 1, x0:x1 + 1]
front[~m] = (245, 245, 245)
# back: remove the chest print (dark strokes in the upper-middle band) and keep seams/outline
back = front.copy(); h, w = back.shape[:2]
band = np.zeros((h, w), np.uint8); band[int(.10 * h):int(.45 * h), int(.18 * w):int(.82 * w)] = 1
dark = (cv2.cvtColor(back, cv2.COLOR_BGR2GRAY) < 215).astype(np.uint8) & band
back = cv2.inpaint(back, cv2.dilate(dark, np.ones((5, 5), np.uint8)), 5, cv2.INPAINT_TELEA)
back = cv2.flip(back, 1)
atlas = np.hstack([front, back]); cv2.imwrite(str(P / "tee-atlas.png"), atlas)
mesh = trimesh.load(src, force="mesh")
parts = mesh.split(only_watertight=False); mesh = max(parts, key=lambda p: len(p.faces))
if len(mesh.faces) > 40000: mesh = mesh.simplify_quadric_decimation(face_count=40000)
v = mesh.vertices - mesh.bounds.mean(0)
# thinnest axis = depth (z); make y up
# GLB is y-up; keep x = width, y = up, z = depth (front = +z)
# drop thin floaters/sheets far from the body: keep vertices within the robust core extent
core = np.percentile(np.abs(v), 99, axis=0) * 1.15
keepv = (np.abs(v) <= core).all(1)
mesh = trimesh.Trimesh(v, mesh.faces, process=False); mesh.update_faces(keepv[mesh.faces].all(1)); mesh.remove_unreferenced_vertices()
mesh = max(mesh.split(only_watertight=False), key=lambda p: len(p.faces)); v = mesh.vertices - mesh.bounds.mean(0)
if flip: v[:, 0] *= -1
s = 0.72 / np.ptp(v[:, 0]); v *= s
mesh = trimesh.Trimesh(v, mesh.faces, process=True)
fn = mesh.face_normals; vn = mesh.vertex_normals
u = (v[:, 0] - v[:, 0].min()) / np.ptp(v[:, 0]); t = (v[:, 1] - v[:, 1].min()) / np.ptp(v[:, 1])
# duplicate vertices per face so front/back faces can use different atlas halves
F = mesh.faces; V = v[F].reshape(-1, 3); U = u[F].reshape(-1); T = t[F].reshape(-1)
isfront = np.repeat(fn[:, 2] >= 0, 3)
UU = np.where(isfront, U * 0.5, 0.5 + (1 - U) * 0.5); TT = T
newF = np.arange(len(V)).reshape(-1, 3)
tex = Image.fromarray(cv2.cvtColor(atlas, cv2.COLOR_BGR2RGB))
mat = trimesh.visual.material.PBRMaterial(baseColorTexture=tex, metallicFactor=0.0, roughnessFactor=0.9, doubleSided=True)
out_mesh = trimesh.Trimesh(V, newF, process=False, visual=trimesh.visual.TextureVisuals(uv=np.c_[UU, TT], material=mat))
out_mesh = out_mesh.simplify_quadric_decimation(face_count=min(len(newF), 60000)) if False else out_mesh
out_mesh.export(out)
# preview colors (face centroids sampled from atlas)
fu = np.c_[UU, TT].reshape(-1, 3, 2).mean(1); H, Wd = atlas.shape[:2]
col = atlas[np.clip(((1 - fu[:, 1]) * (H - 1)).astype(int), 0, H - 1), np.clip((fu[:, 0] * (Wd - 1)).astype(int), 0, Wd - 1)][:, ::-1]
np.save(out.replace(".glb", "-facecolors.npy"), col)
print(out, len(newF), "faces; size m", np.ptp(v, 0).round(3).tolist(), "front faces", int((fn[:, 2] >= 0).sum()))
