"""Phase L: SAM 3 client masks for every v003 shot (only the selected shots, not the library).

usage: masks_v003.py CLIENT [--fps 15]
For each shot in work/v003/<client>/plan.json: decode [t_in - 0.3, t_in + dur + 0.3] at --fps, prompt
Sam3TrackerVideoModel with the client's track box on the first frame that has one, propagate, then
re-prompt (box from the track) on frames whose mask/box IoU < 0.3 (drift guard, at most one prompt per
second) and propagate again. Writes work/v003/<client>/masks/<key>.npz (packbits masks, times) and
masks.json with per-shot quality: median IoU vs track, % frames < 0.3, empty masks, area jumps > 30 %.
"""
import sys, json, time, pathlib, argparse
import numpy as np, cv2, torch
from transformers import Sam3TrackerVideoModel, Sam3TrackerVideoProcessor

ROOT = pathlib.Path(__file__).resolve().parent
ap = argparse.ArgumentParser(); ap.add_argument('client'); ap.add_argument('--fps', type=float, default=15)
a = ap.parse_args()
wd = ROOT / 'work' / 'v003' / a.client; (wd / 'masks').mkdir(parents=True, exist_ok=True)
plan = json.load(open(wd / 'plan.json'))
shots = []
for d in plan['days']:
    shots += [s for s in [d['arrival']] + d['sets'] + [d['peak']] if s]
shots += [s for s in (plan['hero'], plan['finale']) if s]
dev = 'cuda'
model = Sam3TrackerVideoModel.from_pretrained('facebook/sam3', torch_dtype=torch.bfloat16).to(dev)
proc = Sam3TrackerVideoProcessor.from_pretrained('facebook/sam3')


def key(s):
    return f"{s['day']}_{s['clip']}_{s['t_in']:.2f}"


def iou(b, mb):
    ix = max(0, min(b[2], mb[2]) - max(b[0], mb[0])) * max(0, min(b[3], mb[3]) - max(b[1], mb[1]))
    u = (b[2] - b[0]) * (b[3] - b[1]) + (mb[2] - mb[0]) * (mb[3] - mb[1]) - ix
    return ix / u if u > 0 else 0


def run(frames, prompts):
    sess = proc.init_video_session(video=frames, inference_device=dev, processing_device='cpu', video_storage_device='cpu',
                                   inference_state_device=dev, dtype=torch.bfloat16)
    for fi, box in prompts:
        proc.add_inputs_to_inference_session(inference_session=sess, frame_idx=fi, obj_ids=1, input_boxes=[[box]])
        model(inference_session=sess, frame_idx=fi)
    M = {}
    for out in model.propagate_in_video_iterator(sess, start_frame_idx=prompts[0][0]):
        m = proc.post_process_masks([out.pred_masks], original_sizes=[[720, 1280]], binarize=True)[0]
        M[out.frame_idx] = m[0, 0].cpu().numpy().astype(bool)
    if prompts[0][0] > 0:  # frames before the first prompt: propagate backwards
        for out in model.propagate_in_video_iterator(sess, start_frame_idx=prompts[0][0], reverse=True):
            if out.frame_idx not in M:
                m = proc.post_process_masks([out.pred_masks], original_sizes=[[720, 1280]], binarize=True)[0]
                M[out.frame_idx] = m[0, 0].cpu().numpy().astype(bool)
    return np.stack([M.get(i, np.zeros((720, 1280), bool)) for i in range(len(frames))])


report = json.load(open(wd / 'masks.json')) if (wd / 'masks.json').exists() else {}
for s in shots:
    k = key(s)
    if (wd / 'masks' / f'{k}.npz').exists() and k in report:
        continue
    clip = ROOT / 'source' / a.client / s['day'] / 'clips' / f"{s['clip']}.mp4"
    B = json.load(open(clip.with_suffix('.track.json')))['boxes']
    cf = [b for b in B if b['status'] == 'confirmed' and s['t_in'] - 1 <= b['t'] <= s['t_in'] + s['dur'] + 1]
    B = [b for b in B if b['status'] == 'confirmed'] if cf else B
    def tbox(t):
        b = min(B, key=lambda x: abs(x['t'] - t)); return b['box'] if abs(b['t'] - t) < 0.6 else None
    cap = cv2.VideoCapture(str(clip)); vf = cap.get(5)
    t0, t1 = max(0, s['t_in'] - 0.3), s['t_in'] + s['dur'] + 0.3
    cap.set(1, int(t0 * vf)); f = int(t0 * vf); nxt = f; frames, times = [], []
    while f <= t1 * vf:
        ok, img = cap.read()
        if not ok: break
        if f >= nxt: frames.append(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)); times.append(f / vf); nxt += vf / a.fps
        f += 1
    first = next((i for i, t in enumerate(times) if tbox(t) is not None), None)
    if first is None:
        print('no box', k); continue
    tic = time.time(); prompts = [(first, tbox(times[first]))]
    for it in range(3):
        M = run(frames, prompts)
        ious, low = [], []
        for i, t in enumerate(times):
            b = tbox(t)
            if b is None: continue
            if not M[i].any(): ious.append(0); low.append(i); continue
            ys, xs = np.nonzero(M[i]); v = iou(b, [xs.min(), ys.min(), xs.max(), ys.max()]); ious.append(v)
            if v < 0.3: low.append(i)
        new = []
        for i in low:
            if all(abs(i - p) >= a.fps for p, _ in prompts + new): new.append((i, tbox(times[i])))
        if not new or it == 2: break
        prompts = sorted(prompts + new)
    area = M.reshape(len(M), -1).sum(1)
    jumps = int((np.abs(np.diff(area)) / np.maximum(area[:-1], 1) > 0.3).sum())
    np.savez_compressed(wd / 'masks' / f'{k}.npz', masks=np.packbits(M, axis=-1), times=np.array(times))
    report[k] = {'kind': s['kind'], 'frames': len(frames), 'secs': round(time.time() - tic, 1), 'prompts': len(prompts),
                 'iou_median': round(float(np.median(ious)), 3) if ious else None,
                 'iou_lt_0_3': round(float(np.mean(np.array(ious) < 0.3)), 3) if ious else None,
                 'empty': int((area == 0).sum()), 'area_jumps': jumps}
    json.dump(report, open(wd / 'masks.json', 'w'), indent=1)
    print(k, report[k], flush=True)
    torch.cuda.empty_cache()
print('MASKS DONE', len(report))
