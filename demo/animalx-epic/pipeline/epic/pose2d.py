"""2D pose for the client in one source clip.

Interpolates the confirmed 5 fps track box to every frame, runs RTMPose (body7, COCO-17)
on that box only, and writes <clip>.pose.json with keypoints, scores and joint angles.
"""
import sys, os, json, math, time, cv2, numpy as np
DEV = os.environ.get('POSE_DEVICE', 'cuda')
if DEV == 'cuda':
    import onnxruntime as ort; ort.preload_dlls()
from rtmlib import RTMPose
_MODEL = None

MODEL = ('https://download.openmmlab.com/mmpose/v1/projects/rtmposev1/onnx_sdk/'
         'rtmpose-l_simcc-body7_pt-body7_420e-384x288-3f5a1437_20230504.zip')
KP = ['nose', 'leye', 'reye', 'lear', 'rear', 'lsho', 'rsho', 'lelb', 'relb', 'lwri', 'rwri',
      'lhip', 'rhip', 'lkne', 'rkne', 'lank', 'rank']
ANG = {'l_elbow': (5, 7, 9), 'r_elbow': (6, 8, 10), 'l_shoulder': (11, 5, 7), 'r_shoulder': (12, 6, 8),
       'l_hip': (5, 11, 13), 'r_hip': (6, 12, 14), 'l_knee': (11, 13, 15), 'r_knee': (12, 14, 16)}


def angle(a, b, c):
    v1, v2 = a - b, c - b
    n = np.linalg.norm(v1) * np.linalg.norm(v2)
    return float(math.degrees(math.acos(np.clip(v1 @ v2 / n, -1, 1)))) if n > 0 else None


def boxes_per_frame(track, n, fps):
    B = [b for b in track['boxes']]
    ts = np.array([b['t'] for b in B]); bx = np.array([b['box'] for b in B], float)
    out = []
    for f in range(n):
        t = f / fps
        if t < ts[0] - 0.5 or t > ts[-1] + 0.5:
            out.append(None); continue
        i = np.searchsorted(ts, t)
        if i == 0 or i >= len(ts):
            out.append(bx[min(i, len(ts) - 1)]); continue
        if ts[i] - ts[i - 1] > 1.5:  # gap in track: no box
            out.append(None); continue
        w = (t - ts[i - 1]) / (ts[i] - ts[i - 1]); out.append(bx[i - 1] * (1 - w) + bx[i] * w)
    return out


def main(clip):
    if not os.path.exists(clip) or not os.path.exists(clip[:-4] + '.track.json'):
        print('missing', clip); return
    if os.path.exists(clip[:-4] + '.pose.json') and '--force' not in sys.argv:
        print('skip', clip); return
    track = json.load(open(clip[:-4] + '.track.json'))
    cap = cv2.VideoCapture(clip); fps = cap.get(5); n = int(cap.get(7))
    boxes = boxes_per_frame(track, n, fps)
    global _MODEL
    if _MODEL is None:
        _MODEL = RTMPose(MODEL, model_input_size=(288, 384), backend='onnxruntime', device=DEV)
    model = _MODEL
    frames = []; t0 = time.time()
    for f in range(n):
        ok, img = cap.read()
        if not ok: break
        b = boxes[f]
        if b is None:
            frames.append(None); continue
        x0, y0, x1, y1 = b; pw, ph = (x1 - x0) * 0.15, (y1 - y0) * 0.1
        kp, sc = model(img, bboxes=[[x0 - pw, y0 - ph, x1 + pw, y1 + ph]])
        kp, sc = kp[0], sc[0]
        ang = {k: (angle(kp[a], kp[b_], kp[c]) if min(sc[a], sc[b_], sc[c]) > 0.3 else None)
               for k, (a, b_, c) in ANG.items()}
        frames.append({'t': round(f / fps, 3), 'box': [round(v, 1) for v in b],
                       'kp': np.round(kp, 1).tolist(), 'sc': np.round(sc, 3).tolist(), 'ang': ang})
    dt = time.time() - t0
    json.dump({'clip': clip, 'fps': fps, 'model': MODEL.rsplit('/', 1)[1], 'kp_names': KP, 'frames': frames},
              open(clip[:-4] + '.pose.json', 'w'))
    ok = [f for f in frames if f]
    print(f'{clip}: {len(ok)}/{len(frames)} frames posed in {dt:.0f}s; mean conf {np.mean([np.mean(f["sc"]) for f in ok]):.2f}')


if __name__ == '__main__':
    for c in sys.argv[1:]:
        if c.endswith('.mp4'): main(c)
