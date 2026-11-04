#!/usr/bin/env python3
"""SAM 3 text-prompted (args: step_frames prompts_csv tag window_end_s) segmentation at 1 fps over the analysis window (recordings 1-8, to 7544 s).
Prompts: 'garment' (material) and 'person'. One image encoding per frame, reused for both prompts.
Masks stored as simplified normalized polygons + score + area; no raw frames written."""
import gzip, json, time, sys
from pathlib import Path
import av, numpy as np, torch, cv2
from PIL import Image
from transformers import Sam3Processor, Sam3Model

ROOT = Path(__file__).resolve().parents[1]
VR = ROOT / "enpiso/video-review"
OUT = VR / "media/vision-analysis/sam3"; OUT.mkdir(parents=True, exist_ok=True)
WINDOW_END = 7544.0
STEP = int(sys.argv[1]) if len(sys.argv) > 1 else 15  # frames (15 = 1 fps)
PROMPTS = sys.argv[2].split(",") if len(sys.argv) > 2 else ["garment", "person"]
TAG = sys.argv[3] if len(sys.argv) > 3 else "sam3"
WINDOW_END = float(sys.argv[4]) if len(sys.argv) > 4 else WINDOW_END

proc = Sam3Processor.from_pretrained("facebook/sam3")
model = Sam3Model.from_pretrained("facebook/sam3", torch_dtype=torch.float16).cuda().eval()
text_inputs = {p: proc(text=p, return_tensors="pt").to("cuda") for p in PROMPTS}


def polys(mask):
    cs, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    H, W = mask.shape; out = []
    for c in cs:
        if cv2.contourArea(c) < 40:
            continue
        c = cv2.approxPolyDP(c, 1.5, True).reshape(-1, 2)
        out.append([round(v, 4) for xy in c for v in (xy[0] / W, xy[1] / H)])
    return out

pl = json.load(open(VR / "full-playlist.json"))
t0 = time.time(); n = 0
for r in pl["recordings"]:
    if r["timelineStart"] >= WINDOW_END:
        break
    outf = OUT / f"{TAG}-rec{r['id']:02d}.jsonl.gz"
    if outf.exists() and outf.stat().st_size > 0 and (OUT / f"{TAG}-rec{r['id']:02d}.done").exists():
        continue
    f = gzip.open(outf, "wt")
    c = av.open(str(VR / "media/full-playlist-v1" / r["file"])); s = c.streams.video[0]; s.thread_type = "AUTO"
    for fr in c.decode(s):
        idx = round(float(fr.pts * s.time_base) * 15)
        if r["timelineStart"] + idx / 15 > WINDOW_END:
            break
        if idx % STEP:
            continue
        img = fr.to_image()
        with torch.no_grad():
            pv = proc(images=img, return_tensors="pt")
            pix = pv["pixel_values"].to("cuda", torch.float16)
            vis = model.get_vision_features(pixel_values=pix)
            rec = {"rec": r["id"], "frame": idx, "t": round(r["timelineStart"] + idx / 15, 3)}
            for p in PROMPTS:
                ti = text_inputs[p]
                o = model(vision_embeds=vis, input_ids=ti["input_ids"], attention_mask=ti["attention_mask"])
                res = proc.post_process_instance_segmentation(o, threshold=0.4, mask_threshold=0.5, target_sizes=pv["original_sizes"].tolist())[0]
                items = []
                for m_, sc, bx in zip(res["masks"], res["scores"], res["boxes"]):
                    m_ = m_.cpu().numpy().astype(bool)
                    items.append({"s": round(float(sc), 3), "a": round(float(m_.mean()), 5),
                                  "b": [round(float(v), 4) for v in (bx.cpu().numpy() / [img.width, img.height, img.width, img.height])],
                                  "poly": polys(m_)})
                rec[p] = items
        f.write(json.dumps(rec) + "\n"); n += 1
        if n % 200 == 0:
            el = time.time() - t0
            print(json.dumps({"rec": r["id"], "frames": n, "elapsed_s": round(el, 1), "fps": round(n / el, 2),
                              "eta_min_remaining_of_7544": round((7544 * 15 / STEP - n) / (n / el) / 60, 1),
                              "peak_vram_gib": round(torch.cuda.max_memory_allocated() / 2**30, 2)}), flush=True)
    f.close(); c.close(); (OUT / f"{TAG}-rec{r['id']:02d}.done").touch()
print("done", n, round(time.time() - t0, 1))
