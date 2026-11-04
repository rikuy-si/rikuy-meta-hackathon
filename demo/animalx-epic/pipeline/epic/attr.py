"""Phase D: cloth-independent attribute search (bald head) with zero-shot CLIP ViT-L/14 on head crops.

usage: attr.py CLIENT DAY CAM [--t0 S --t1 S] [--top 30] [--sheet OUT.jpg] [--eval]
Head region = top 24% of each person crop (full width). Track score = mean of the best half of its crops'
P(bald). --eval reports how the client's labeled positive tracks rank (on a labeled day), to check the cue.
Writes source/<client>/<day>/matches/bald_<cam>.json.
"""
import sys, json, pathlib, argparse, subprocess, collections
import numpy as np, torch, cv2
from transformers import CLIPModel, CLIPProcessor

ROOT = pathlib.Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument('client'); ap.add_argument('day'); ap.add_argument('cam')
ap.add_argument('--t0', type=float, default=0); ap.add_argument('--t1', type=float, default=86400)
ap.add_argument('--top', type=int, default=30); ap.add_argument('--sheet'); ap.add_argument('--eval', action='store_true')
ap.add_argument('--per-track', type=int, default=8)
a = ap.parse_args()
base = ROOT / 'source' / a.client / a.day
cd = base / 'tracks' / a.cam / 'crops'
g = collections.defaultdict(list)
for p in sorted(cd.glob('*.jpg')):
    t = int(p.name[7:13]) / 10
    if a.t0 <= t <= a.t1:
        g[int(p.name[:6])].append(p)
g = {t: [ps[i] for i in sorted(set(np.linspace(0, len(ps) - 1, min(a.per_track, len(ps))).round().astype(int)))] for t, ps in g.items() if len(ps) >= 3}
dev = 'cuda'
mid = 'openai/clip-vit-large-patch14'
model = CLIPModel.from_pretrained(mid, torch_dtype=torch.float16).to(dev).eval(); proc = CLIPProcessor.from_pretrained(mid)
prompts = ['a CCTV photo of the top of a bald shaved head', 'a CCTV photo of a bald man seen from above',
           'a CCTV photo of a head with dark hair', 'a CCTV photo of a person with long hair', 'a CCTV photo of a person wearing a cap']
with torch.no_grad():
    ti = proc(text=prompts, return_tensors='pt', padding=True).to(dev)
    T = model.get_text_features(**ti); T = getattr(T, 'pooler_output', T) if not torch.is_tensor(T) else T
    T = model.text_projection(T) if T.shape[-1] != model.config.projection_dim else T
    T = T / T.norm(dim=-1, keepdim=True)
flat = [(t, p) for t, ps in g.items() for p in ps]
probs = []
B = 256
for i in range(0, len(flat), B):
    ims = []
    for _, p in flat[i:i + B]:
        im = cv2.imread(str(p))[:, :, ::-1]
        h = im.shape[0]; head = im[:max(8, int(h * 0.24))]
        ims.append(np.ascontiguousarray(head))
    with torch.no_grad():
        x = proc(images=ims, return_tensors='pt').to(dev)
        I = model.get_image_features(pixel_values=x['pixel_values'].half())
        I = I if torch.is_tensor(I) else I.pooler_output
        I = model.visual_projection(I) if I.shape[-1] != model.config.projection_dim else I
        I = I / I.norm(dim=-1, keepdim=True)
        pr = (100 * I @ T.T).softmax(-1).float().cpu().numpy()
    probs.append(pr[:, :2].sum(1))
probs = np.concatenate(probs) if probs else np.zeros(0)
tids = np.array([t for t, _ in flat])
res = {}
for t in g:
    v = np.sort(probs[tids == t])[::-1]
    res[int(t)] = float(v[:max(1, (len(v) + 1) // 2)].mean())
order = sorted(res, key=res.get, reverse=True)
json.dump(res, open(base / 'matches' / f'bald_{a.cam}.json', 'w'))
print(len(res), 'tracks; top:', [(t, round(res[t], 2)) for t in order[:a.top]])
if a.eval:
    lab = json.load(open(base / 'labels.json')).get(a.cam, {})
    pos = [t for t in order if lab.get(str(t)) == 1]
    ranks = [order.index(t) for t in pos]
    print(f'client positives: {len(pos)}; median rank {np.median(ranks):.0f} of {len(order)}; in top 10%: {np.mean(np.array(ranks) < len(order) * 0.1):.2f}')
if a.sheet:
    subprocess.run([sys.executable, str(ROOT / 'review.py'), a.client, a.day, a.cam, a.sheet, '--tids', *map(str, order[:a.top])], check=True)
