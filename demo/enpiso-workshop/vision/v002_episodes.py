#!/usr/bin/env python3
"""Detect candidate role episodes from per-second signals and render review sheets.
Episodes: B_face (B torso turned toward camera), B_front (B at A's front table), A_up (A standing, away from seat).
Writes v002/episodes.json and v002/review/<kind>-NN.jpg (8 episodes per sheet)."""
import sys, os
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from v002_common import *
import cv2

TMAX = 5760
z = np.load(V2 / "signals.npz"); S = {k: z[k] for k in z}


def runs(mask, minlen=2, gap=2):
    out = []; st = None; last = None
    for i, m in enumerate(mask):
        if m:
            if st is None or i - last > gap:
                if st is not None and last - st + 1 >= minlen: out.append([st, last + 1])
                st = i
            last = i
    if st is not None and last - st + 1 >= minlen: out.append([st, last + 1])
    return out


def episodes():
    E = []
    for a, b in runs(S["B_sh"] > 0.0, 2):
        E.append(dict(kind="B_face", start=a, end=b, cx=float(np.nanmedian(S["B_cx"][a:b]))))
    for a, b in runs(S["B_cx"] < 0.56, 2):
        E.append(dict(kind="B_front", start=a, end=b, cx=float(np.nanmedian(S["B_cx"][a:b]))))
    for a, b in runs((S["A_cx"] >= 0.44) & (S["A_hgt"] >= 0.36), 2):
        E.append(dict(kind="A_up", start=a, end=b, cx=float(np.nanmedian(S["A_cx"][a:b]))))
    E.sort(key=lambda e: (e["start"], e["kind"]))
    for i, e in enumerate(E): e["id"] = f"{e['kind']}-{i:03d}"
    return E


if __name__ == "__main__":
    E = episodes()
    json.dump(E, open(V2 / "episodes.json", "w"), indent=1)
    kinds = sys.argv[1:] or ["B_face", "B_front", "A_up"]
    fr = Frames(); out = V2 / "review"; out.mkdir(exist_ok=True)
    CROP = (300, 300, 1340, 810); TWW = 300
    for kind in kinds:
        L = [e for e in E if e["kind"] == kind]
        rows = []
        for n, e in enumerate(L):
            a, b = e["start"], e["end"]
            ts = [a - 3, a, (a + b) / 2, b, b + 3, b + 7]
            tiles = []
            for t in ts:
                img = fr.get(max(0.0, t))[CROP[1]:CROP[3], CROP[0]:CROP[2]]
                sc = TWW / img.shape[1]; img = cv2.resize(img, (TWW, int(img.shape[0] * sc)))
                cv2.rectangle(img, (0, 0), (TWW, 18), (0, 0, 0), -1)
                cv2.putText(img, f"{e['id']} t={t:.0f} ({t-a:+.0f})", (3, 13), 0, 0.42, (255, 255, 255), 1)
                tiles.append(img)
            rows.append(np.hstack(tiles))
            if len(rows) == 6 or n == len(L) - 1:
                cv2.imwrite(str(out / f"{kind}-{n // 6:02d}.jpg"), np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 82]); rows = []
        print(kind, len(L))
