"""Split SAM 3 'garment' instances into worn/held (mostly inside a 'person' mask) vs surface material.
Rasterizes polygons at 1/4 resolution (360x203)."""
import numpy as np, cv2

W, H = 360, 203


def raster(polys):
    m = np.zeros((H, W), np.uint8)
    for p in polys:
        a = np.array(p, np.float32).reshape(-1, 2) * [W, H]
        if len(a) >= 3:
            cv2.fillPoly(m, [a.astype(np.int32)], 1)
    return m


def split(frame, min_score=0.45, contain=0.6):
    """Return (surface, on_person) lists of garment instances for one SAM 3 frame record."""
    pm = np.zeros((H, W), np.uint8)
    for p in frame.get("person", []):
        if p["s"] >= 0.4:
            pm |= raster(p["poly"])
    surf, onp = [], []
    for g in frame.get("garment", []):
        if g["s"] < min_score:
            continue
        gm = raster(g["poly"]); area = gm.sum()
        if area == 0:
            continue
        frac = (gm & pm).sum() / area
        (onp if frac >= contain else surf).append({**g, "personOverlap": round(float(frac), 2)})
    return surf, onp
