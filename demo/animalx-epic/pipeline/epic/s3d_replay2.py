"""SAM 3D Body replay v2 of the finale's last reps: solid lit mesh instead of a point cloud.

usage: PYOPENGL_PLATFORM=egl s3d_replay2.py CLIENT [--fps 15] [--reps 2]
Fits SAM 3D Body on the client's (expanded) track box for the last --reps reps of the finale shot, smooths
vertices over time, and renders two 960x1080 panels per frame into work/v003/<client>/s3db2/:
  ov_###.png  the real CCTV frame (cropped on the client) with the mesh overlaid (official SAM 3D Body look)
  rl_###.png  the real CCTV crop on the client (no overlay)
  st_###.png  a studio view. --mode bench (auto for bench/incline/floor press): torso locked on a bench, chest up,
              level bar at the palms. --mode standing (others, e.g. thruster): feet locked on the floor, dumbbells
              along the knuckle line. Bar, bench and dumbbells are illustrative props, not model output.
meta.json also stores freeze_t: the source time with the arms most extended (best freeze frame).
Runs in the tejiendo-sam3d-body venv.
"""
import os, sys, json, math, pathlib, argparse
os.environ.setdefault('PYOPENGL_PLATFORM', 'egl')
import numpy as np, cv2, trimesh, pyrender
from scipy.ndimage import gaussian_filter1d
sys.path.insert(0, os.environ['SAM3D_BODY_REPO'])  # clone of facebookresearch/sam-3d-body
from sam_3d_body import load_sam_3d_body, SAM3DBodyEstimator
from sam_3d_body.visualization.renderer import Renderer

ROOT = pathlib.Path(__file__).resolve().parent
ap = argparse.ArgumentParser(); ap.add_argument('client'); ap.add_argument('--fps', type=float, default=15)
ap.add_argument('--reps', type=int, default=2)
ap.add_argument('--mode', choices=['auto', 'bench', 'standing'], default='auto')
a = ap.parse_args()
S = os.environ['SAM3D_BODY_CKPT']  # snapshot dir of facebook/sam-3d-body-vith
wd = ROOT / 'work' / 'v003' / a.client; out = wd / 's3db2'; out.mkdir(parents=True, exist_ok=True)

fin = json.load(open(wd / 'plan.json'))['finale']
R = [fin['t_in'] + r for r in fin['rep_times']]
t0 = R[-1 - a.reps] if len(R) > a.reps else R[0] - 2.0
t1 = R[-1] + 0.8
clip = ROOT / 'source' / a.client / fin['day'] / 'clips' / f"{fin['clip']}.mp4"
B = [b for b in json.load(open(clip.with_suffix('.track.json')))['boxes'] if b['status'] == 'confirmed']
model, cfg = load_sam_3d_body(S + '/model.ckpt', device='cuda', mhr_path=S + '/assets/mhr_model.pt')
est = SAM3DBodyEstimator(sam_3d_body_model=model, model_cfg=cfg)
faces = est.faces
cap = cv2.VideoCapture(str(clip)); vf = cap.get(5)
ts = np.arange(t0, t1, 1 / a.fps)
frames, V, K, CT, FL, BX = [], [], [], [], [], []
cache = out / 'fits.npz'
if cache.exists():
    z = np.load(cache); V, K, CT, FL, BX = list(z['V']), list(z['K']), list(z['CT']), list(z['FL']), list(z['BX'])
    for t in ts:
        cap.set(1, int(round(t * vf))); frames.append(cap.read()[1])
for t in ([] if cache.exists() else ts):
    cap.set(1, int(round(t * vf))); ok, img = cap.read()
    x1, y1, x2, y2 = min(B, key=lambda x: abs(x['t'] - t))['box']
    w, h = x2 - x1, y2 - y1
    bb = [max(0, x1 - .1 * w), max(0, y1 - .1 * h), min(1279, x2 + .1 * w), min(719, y2 + .1 * h)]
    o = est.process_one_image(cv2.cvtColor(img, cv2.COLOR_BGR2RGB), bboxes=np.array([bb], float))[0]
    frames.append(img); V.append(o['pred_vertices']); K.append(o['pred_keypoints_3d']); CT.append(o['pred_cam_t'])
    FL.append(float(o['focal_length'])); BX.append(bb)
V, K, CT = np.stack(V), np.stack(K), np.stack(CT)
np.savez(cache, V=V, K=K, CT=CT, FL=np.array(FL), BX=np.array(BX))
# temporal smoothing (camera space = model space + cam_t)
Vc = gaussian_filter1d(V + CT[:, None], 1.0, axis=0); Kc = gaussian_filter1d(K + CT[:, None], 1.0, axis=0)
CTs = gaussian_filter1d(CT, 1.0, axis=0)
focal = float(np.median(FL))

# ---------- overlay panels (official look): mesh rendered in the CCTV camera, cropped on the client
BXa = np.array(BX); cx, cy = BXa[:, [0, 2]].mean(), BXa[:, [1, 3]].mean()
ch = float(np.clip(max(np.ptp(BXa[:, [1, 3]]), np.ptp(BXa[:, [0, 2]]) * 9 / 8) * 1.25, 240, 720)); cw = ch * 8 / 9
X0 = int(np.clip(cx - cw / 2, 0, 1280 - cw)); Y0 = int(np.clip(cy - ch / 2, 0, 720 - ch))
rend = Renderer(focal_length=focal, faces=faces)
GOLD = (1.0, 0.78, 0.25)   # RGB
OSD_LABEL = np.zeros((720, 1280), np.uint8); OSD_LABEL[632:670, 914:1070] = 255   # burned-in 'Camera 0X' label
frames = [cv2.inpaint(f_, OSD_LABEL, 5, cv2.INPAINT_TELEA) for f_ in frames]
for i, img in enumerate(frames):
    rgba = rend(Vc[i] - CTs[i], CTs[i], img.astype(np.float32), mesh_base_color=GOLD, return_rgba=True)
    al = rgba[..., 3:4] * 0.85
    comp = img.astype(np.float32) / 255 * (1 - al) + rgba[..., :3] * al
    crop = (comp[Y0:Y0 + int(ch), X0:X0 + int(cw)] * 255).astype(np.uint8)
    cv2.imwrite(str(out / f'rl_{i:03d}.png'), cv2.resize(img[Y0:Y0 + int(ch), X0:X0 + int(cw)], (960, 1080), interpolation=cv2.INTER_CUBIC))
    cv2.imwrite(str(out / f'ov_{i:03d}.png'), cv2.resize(crop, (960, 1080), interpolation=cv2.INTER_CUBIC))

MODE = a.mode if a.mode != 'auto' else ('bench' if any(k in fin['exercise'] for k in ('banca', 'inclinado', 'suelo')) else 'standing')
LS, RS, LH, RH, NECK, LW, RW, LK, RK = 5, 6, 9, 10, 69, 62, 41, 53, 32
NOSE, LA, RA, LI, LP, RI, RP = 0, 13, 14, 49, 61, 28, 40
FEET = list(range(13, 21))
Vm, Km = V.copy(), K.copy()                                   # model space (root-relative, no cam_t)


def kabsch(P, Q):                                              # R, t with R @ P + t ~= Q
    pc, qc = P.mean(0), Q.mean(0); U, _, Wt = np.linalg.svd((P - pc).T @ (Q - qc))
    D = np.diag([1, 1, np.sign(np.linalg.det(Wt.T @ U.T))]); R = Wt.T @ D @ U.T
    return R, qc - R @ pc


def lock(idx):
    """Rigidly align every frame on the vertices idx (Kabsch, no scale) to their mean aligned position."""
    ref = len(Vm) // 2; target_t = Vm[ref, idx]
    for _ in range(2):
        A = [kabsch(Vm[i, idx], target_t) for i in range(len(Vm))]
        target_t = np.mean([Vm[i, idx] @ R_.T + t_ for i, (R_, t_) in enumerate(A)], axis=0)
    Va = np.stack([Vm[i] @ R_.T + t_ for i, (R_, t_) in enumerate(A)]); Ka = np.stack([Km[i] @ R_.T + t_ for i, (R_, t_) in enumerate(A)])
    resid = np.array([np.sqrt(((Va[i, idx] - target_t) ** 2).sum(1).mean()) for i in range(len(Va))])
    return Va, Ka, resid


if MODE == 'bench':
    # The model estimates depth and global rotation per frame; from a top-down CCTV view they jitter (hip moved up to
    # 34 cm between frames). On a bench press the torso does not move relative to the bench: lock the torso.
    k = Km[len(Km) // 2]; hp = (k[LH] + k[RH]) / 2; ax = k[NECK] - hp; L = np.linalg.norm(ax); ax /= L
    rel = Vm[len(Vm) // 2] - hp; tt = rel @ ax / L; dist = np.linalg.norm(rel - np.outer(rel @ ax, ax), axis=1)
    TI = np.where((tt > 0.0) & (tt < 0.85) & (dist < 0.16))[0]
    Va, Ka, resid = lock(TI)
    k0 = Ka.mean(0); hip0 = (k0[LH] + k0[RH]) / 2; spine0 = k0[NECK] - hip0; across0 = k0[RS] - k0[LS]
    up = np.cross(spine0, across0); up /= np.linalg.norm(up)       # chest direction = world up
    lon = spine0 - up * spine0.dot(up); lon /= np.linalg.norm(lon)  # hips -> head
    Rw = np.stack([lon, up, np.cross(lon, up)]); org = ((k0[LS] + k0[RS]) / 2 + hip0) / 2
else:
    # Standing lift (thruster): the feet do not move; lock the feet, the body squats and presses above them.
    k = Km[len(Km) // 2]
    d2 = np.min(np.linalg.norm(Vm[len(Vm) // 2][:, None] - k[FEET][None], axis=2), axis=1)
    TI = np.where(d2 < 0.07)[0]
    Va, Ka, resid = lock(TI)
    k0 = Ka.mean(0); ank = (k0[LA] + k0[RA]) / 2
    up = Ka[:, NECK].mean(0) - ank; up /= np.linalg.norm(up)
    right = k0[RS] - k0[LS]; right -= up * right.dot(up); right /= np.linalg.norm(right)
    Rw = np.stack([right, up, np.cross(right, up)]); org = ank
assert np.linalg.det(Rw) > 0                                    # right-handed: no mirrored mesh
Vw = (Va - org) @ Rw.T; Kw = (Ka - org) @ Rw.T
if MODE == 'bench':                                            # light smoothing; heavy on the legs (they rest)
    S1 = gaussian_filter1d(Vw, 1.2, axis=0); S2 = gaussian_filter1d(Vw, 5.0, axis=0)
    hipx = ((Kw[:, LH, 0] + Kw[:, RH, 0]) / 2).mean()
    wl = np.clip((hipx - Vw.mean(0)[:, 0]) / 0.25, 0, 1)[None, :, None]
    Vw = S1 * (1 - wl) + S2 * wl
    base = float(np.percentile(Vw[:, TI, 1], 2))                # lowest back vertices sit on the bench pad
else:
    Vw = gaussian_filter1d(Vw, 1.3, axis=0)
    base = float(np.percentile(Vw[:, TI, 1], 1))                # soles on the floor
Kw = gaussian_filter1d(Kw, 1.2, axis=0)
Vw[:, :, 1] -= base; Kw[:, :, 1] -= base
bench_top, floor = (0.0, -0.45) if MODE == 'bench' else (None, 0.0)
lc = Vw[:, TI].mean(1)
stab = {'mode': MODE, 'locked': 'torso' if MODE == 'bench' else 'feet', 'locked_vertices': int(len(TI)),
        'locked_rms_residual_cm_median': round(float(np.median(resid)) * 100, 2), 'locked_rms_residual_cm_max': round(float(resid.max()) * 100, 2),
        'locked_centroid_frame_move_cm_max': round(float(np.linalg.norm(np.diff(lc, axis=0), axis=1).max()) * 100, 2)}
if MODE == 'bench':
    reach = ((Kw[:, LW, 1] + Kw[:, RW, 1]) / 2) - ((Kw[:, LS, 1] + Kw[:, RS, 1]) / 2)   # wrists above shoulders
else:
    reach = ((Kw[:, LW, 1] + Kw[:, RW, 1]) / 2) - Kw[:, NOSE, 1]                      # wrists above the head
fi = int(np.argmax(reach)); freeze_t = float(ts[fi])


def look_at(eye, target, upv=np.array([0, 1, 0.])):
    f = target - eye; f /= np.linalg.norm(f); r = np.cross(f, upv); r /= np.linalg.norm(r); u = np.cross(r, f)
    M = np.eye(4); M[:3, 0], M[:3, 1], M[:3, 2], M[:3, 3] = r, u, -f, eye
    return M


def cyl(p0, p1, r, color, metal=0.6):
    d = p1 - p0; L = np.linalg.norm(d)
    m = trimesh.creation.cylinder(radius=r, height=L, sections=32)
    m.apply_transform(trimesh.geometry.align_vectors([0, 0, 1], d / L)); m.apply_translation((p0 + p1) / 2)
    return pyrender.Mesh.from_trimesh(m, material=pyrender.MetallicRoughnessMaterial(baseColorFactor=(*color, 1), metallicFactor=metal, roughnessFactor=0.35))


def box(ext, center, color):
    m = trimesh.creation.box(extents=ext); m.apply_translation(center)
    return pyrender.Mesh.from_trimesh(m, material=pyrender.MetallicRoughnessMaterial(baseColorFactor=(*color, 1), metallicFactor=0.1, roughnessFactor=0.8))


def hexrgb(h): return tuple(int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
MENTA, NOCHE, NOCHE2, BRUMA, HIELO = hexrgb('#7FCCB4'), hexrgb('#14133F'), hexrgb('#263962'), hexrgb('#CDD6E8'), hexrgb('#A9B6D3')
body_mat = pyrender.MetallicRoughnessMaterial(baseColorFactor=(*MENTA, 1), metallicFactor=0.1, roughnessFactor=0.5)
bg = np.zeros((1080, 960, 3), np.float32)
yy = np.linspace(0, 1, 1080)[:, None, None]; bg[:] = (np.array([63, 19, 20]) * (1 - yy) + np.array([98, 57, 38]) * yy)   # Noche -> Noche 2 (BGR)
r3 = pyrender.OffscreenRenderer(960, 1080)
if MODE == 'bench':
    bc = Kw[:, [LS, RS, LH, RH], 0].mean()                                        # bench centre along the body
    target = np.array([bc * 0.5, bench_top + 0.25, 0.0])
else:
    target = np.array([0.0, float(Kw[:, NECK, 1].mean()) * 0.68, 0.0])
    fwd = Kw[:, NOSE].mean(0) - Kw[:, NECK].mean(0); fwd[1] = 0; fwd /= np.linalg.norm(fwd)
    rgt = np.cross(np.array([0, 1.0, 0]), fwd)
for i in range(len(Vw)):
    sc = pyrender.Scene(bg_color=[0, 0, 0, 0], ambient_light=(0.25, 0.22, 0.2))
    tm = trimesh.Trimesh(Vw[i], faces, process=False)
    sc.add(pyrender.Mesh.from_trimesh(tm, material=body_mat, smooth=True))
    if MODE == 'bench':
        sc.add(box([1.25, 0.06, 0.32], [bc, bench_top - 0.03, 0], NOCHE2))     # bench pad
        sc.add(box([0.08, bench_top - 0.06 - floor, 0.08], [bc - 0.45, (bench_top - 0.06 + floor) / 2, 0], HIELO))
        sc.add(box([0.08, bench_top - 0.06 - floor, 0.08], [bc + 0.45, (bench_top - 0.06 + floor) / 2, 0], HIELO))
        sc.add(box([6, 0.02, 6], [0, floor - 0.01, 0], tuple(c * 0.45 for c in NOCHE)))               # floor
        w0, w1 = (Kw[i, LW] + 2 * Kw[i, LK]) / 3, (Kw[i, RW] + 2 * Kw[i, RK]) / 3   # palm, not wrist
        mid = (w0 + w1) / 2; mid[1] = max(w0[1], w1[1]) + 0.02; d = np.array([0, 0, 1.0])  # level bar across the body
        sc.add(cyl(mid - d * 1.05, mid + d * 1.05, 0.016, BRUMA, 0.9))      # bar (illustrative)
        for s in (-1, 1):
            sc.add(cyl(mid + d * s * 0.80, mid + d * s * 0.86, 0.15, NOCHE2, 0.3))  # plates
    else:
        sc.add(box([6, 0.02, 6], [0, -0.01, 0], tuple(c * 0.45 for c in NOCHE)))  # floor
        for wr, kn, ix, pk in ((LW, LK, LI, LP), (RW, RK, RI, RP)):         # dumbbell along the knuckle line
            palm = (Kw[i, wr] + 2 * Kw[i, kn]) / 3; ax_ = Kw[i, pk] - Kw[i, ix]; ax_ /= np.linalg.norm(ax_)
            c0 = palm + ax_ * 0.01
            sc.add(cyl(c0 - ax_ * 0.07, c0 + ax_ * 0.07, 0.014, BRUMA, 0.9))
            for s in (-1, 1):
                sc.add(cyl(c0 + ax_ * s * 0.07, c0 + ax_ * s * 0.13, 0.05, NOCHE2, 0.3))
    for k, (az, el) in enumerate([(45, 40), (-60, 25), (180, 30)]):
        L = np.array([math.cos(math.radians(el)) * math.sin(math.radians(az)), math.sin(math.radians(el)),
                      math.cos(math.radians(el)) * math.cos(math.radians(az))])
        sc.add(pyrender.DirectionalLight(color=[1, 1, 1] if k < 2 else list(MENTA), intensity=3.0 if k == 0 else 1.8),
               pose=look_at(L * 5, np.zeros(3)))
    u = i / max(1, len(Vw) - 1)
    if MODE == 'bench':
        az = math.radians(58 - 18 * u)                                            # 3/4 view -> side view
        eye = target + np.array([3.3 * math.sin(az), 1.9, 3.3 * math.cos(az)])
    else:
        az = math.radians(25 + 35 * u)                                            # front 3/4 -> side
        eye = target + (fwd * math.cos(az) + rgt * math.sin(az)) * 4.6 + np.array([0, 0.4, 0])
    sc.add(pyrender.PerspectiveCamera(yfov=math.radians(34)), pose=look_at(eye, target))
    col, _ = r3.render(sc, flags=pyrender.RenderFlags.RGBA)
    al = col[..., 3:4] / 255.0
    im = bg * (1 - al) + col[..., :3][..., ::-1].astype(np.float32) * al
    cv2.imwrite(str(out / f'st_{i:03d}.png'), np.clip(im, 0, 255).astype(np.uint8))
r3.delete()
json.dump({'clip': fin['clip'], 'day': fin['day'], 't0': float(t0), 't1': float(t1), 'fps': a.fps, 'frames': len(Vw),
           'freeze_t': freeze_t, 'focal': focal, 'stability': stab, 'mode': MODE, 'props': 'bench_bar' if MODE == 'bench' else 'dumbbells', 'note': 'bar, bench, dumbbells and floor are illustrative props, not model output'},
          open(out / 'meta.json', 'w'), indent=1)
print('s3d replay2', len(Vw), 'frames', round(t0, 2), round(t1, 2), 'freeze_t', round(freeze_t, 2), stab)
