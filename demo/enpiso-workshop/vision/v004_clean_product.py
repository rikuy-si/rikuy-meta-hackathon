#!/usr/bin/env python3
"""Clean the CP product image ([PRODUCT] '[PRINT]'): remove red callout lines,
upscale x6, segment the garment (flood-fill background from the border), write RGBA + mask."""
import cv2, numpy as np, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "enpiso/.secrets/product-2838/default.webp"
OUT = ROOT / "enpiso/video-review/media/vision-analysis/v004/product"; OUT.mkdir(parents=True, exist_ok=True)
im = cv2.imread(str(SRC))
b, g, r = [im[..., i].astype(int) for i in range(3)]
red = (r > 150) & (r - g > 40) & (r - b > 40)
red = cv2.dilate(red.astype(np.uint8), np.ones((3, 3), np.uint8))
im = cv2.inpaint(im, red, 3, cv2.INPAINT_TELEA)
# the callouts reach the right edge: blank everything right of the sleeve tip
S = 6
big = cv2.resize(im, None, fx=S, fy=S, interpolation=cv2.INTER_LANCZOS4)
big = cv2.detailEnhance(big, sigma_s=5, sigma_r=0.15)
gray = cv2.cvtColor(big, cv2.COLOR_BGR2GRAY)
edges = (gray < 200).astype(np.uint8)
edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
h, w = edges.shape
ff = edges.copy(); mask = np.zeros((h + 2, w + 2), np.uint8)
for x, y in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1), (w // 2, 0), (w // 2, h - 1)]:
    if ff[y, x] == 0: cv2.floodFill(ff, mask, (x, y), 2)
garment = (ff != 2).astype(np.uint8)
n, lab, st, _ = cv2.connectedComponentsWithStats(garment)
k = 1 + np.argmax(st[1:, cv2.CC_STAT_AREA]); garment = (lab == k).astype(np.uint8)
garment = cv2.morphologyEx(garment, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
cv2.imwrite(str(OUT / "tee-clean.png"), big)
cv2.imwrite(str(OUT / "tee-mask.png"), garment * 255)
rgba = np.dstack([big, garment * 255]); cv2.imwrite(str(OUT / "tee-rgba.png"), rgba)
ov = big.copy(); ov[garment == 0] = (60, 60, 200); cv2.imwrite(str(OUT / "tee-mask-check.png"), ov)
print(big.shape, garment.mean())
