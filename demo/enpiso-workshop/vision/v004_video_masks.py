#!/usr/bin/env python3
"""SAM 3 'white t-shirt' masks on frames where the piece is spread out; writes frame + mask per candidate."""
import sys, json, torch, numpy as np, cv2
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from v002_common import *
from transformers import Sam3Processor, Sam3Model
from PIL import Image
OUT = V2.parent / "v004/video"; OUT.mkdir(parents=True, exist_ok=True)
proc = Sam3Processor.from_pretrained("facebook/sam3")
model = Sam3Model.from_pretrained("facebook/sam3", torch_dtype=torch.float16).cuda().eval()
fr = Frames(); res = []
for t in [float(x) for x in sys.argv[1:]]:
    img = fr.get(t); pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    best = None
    for prompt in ("white t-shirt", "white shirt", "white garment"):
        inp = proc(images=pil, text=prompt, return_tensors="pt").to("cuda")
        inp = {k: (v.half() if v.dtype == torch.float32 else v) for k, v in inp.items()}
        with torch.no_grad(): o = model(**inp)
        r = proc.post_process_instance_segmentation(o, threshold=0.4, mask_threshold=0.5, target_sizes=inp["original_sizes"].tolist())[0]
        for m, s in zip(r["masks"], r["scores"]):
            m = m.cpu().numpy().astype(bool); a = m.mean()
            if a < 0.004 or a > 0.12: continue
            sc = float(s) * np.sqrt(a)
            if best is None or sc > best[0]: best = (sc, float(s), float(a), prompt, m)
    if best is None: print(t, "no mask"); continue
    tag = f"t{int(t):05d}"
    cv2.imwrite(str(OUT / f"{tag}.png"), img); cv2.imwrite(str(OUT / f"{tag}-mask.png"), best[4].astype(np.uint8) * 255)
    ov = img.copy(); ov[best[4]] = (0.5 * ov[best[4]] + [0, 0, 127]).astype(np.uint8); ys, xs = np.where(best[4])
    cv2.imwrite(str(OUT / f"{tag}-check.jpg"), ov[max(0, ys.min() - 60):ys.max() + 60, max(0, xs.min() - 60):xs.max() + 60])
    res.append(dict(t=t, tag=tag, score=round(best[1], 3), area=round(best[2], 4), prompt=best[3])); print(res[-1], flush=True)
json.dump(res, open(OUT / "masks.json", "w"), indent=1)
