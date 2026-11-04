#!/usr/bin/env python3
"""Per-second role signals for v0.0.2 (CPU, existing 5 fps pose/boxes). Writes v002/signals.npz + a chart."""
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from v002_common import *
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt

TMAX = 5760
P = {l: load_pose(l) for l in "AB"}
sig = {}
for l in "AB":
    z = P[l]; t = z["t"]; b = z["box"].astype(float); k = z["k2"].astype(float); s = z["s"].astype(float)
    sec = np.floor(t).astype(int); ok = sec < TMAX
    cx = np.full(TMAX, np.nan); top = np.full(TMAX, np.nan); hgt = np.full(TMAX, np.nan)
    sh = np.full(TMAX, np.nan)  # shoulder x-order: >0 => left shoulder on image right => facing camera
    hand = np.full(TMAX, np.nan)  # mean wrist speed (normalized units / s)
    wr = np.full((TMAX, 2, 2), np.nan)
    for i in np.where(ok)[0]:
        q = sec[i]
        cx[q] = (b[i, 0] + b[i, 2]) / 2; top[q] = b[i, 1]; hgt[q] = b[i, 3] - b[i, 1]
        if s[i, 5] > .3 and s[i, 6] > .3:
            sh[q] = (k[i, 5, 0] - k[i, 6, 0]) / max(hgt[q], 1e-3)
        for h, ki in enumerate((9, 10)):
            if s[i, ki] > .3: wr[q, h] = k[i, ki]
    sp = np.linalg.norm(np.diff(wr, axis=0), axis=2)  # per-second displacement
    hand[1:] = np.nanmean(sp, axis=1)
    sig[l] = dict(cx=cx, top=top, hgt=hgt, sh=sh, hand=hand, wr=wr)
np.savez_compressed(V2 / "signals.npz", **{f"{l}_{k}": v for l in sig for k, v in sig[l].items()})

if __name__ == "__main__":
    F = [d for d in load_fenix() if d["timeline"] and d["timeline"] < TMAX and d["quantity"] > 0]
    win = int(sys.argv[1]) if len(sys.argv) > 1 else 600
    n = int(np.ceil(TMAX / win))
    fig, ax = plt.subplots(n, 1, figsize=(22, 2.6 * n), sharey=True)
    x = np.arange(TMAX)
    for r in range(n):
        a, b2 = r * win, min(TMAX, (r + 1) * win); A = ax[r]
        A.plot(x[a:b2], sig["A"]["cx"][a:b2], "m.", ms=2, label="A cx")
        A.plot(x[a:b2], 1 - sig["A"]["hgt"][a:b2], "m-", lw=.6, alpha=.5, label="A 1-height (low=standing)")
        A.plot(x[a:b2], sig["B"]["cx"][a:b2], "c.", ms=2, label="B cx")
        A.plot(x[a:b2], 0.5 + 2 * sig["B"]["sh"][a:b2], "k.", ms=1.5, label="B shoulder order (>0.5 facing cam)")
        for d in F:
            if a <= d["timeline"] < b2: A.axvline(d["timeline"], color="r", lw=1.5)
        A.set_xlim(a, a + win); A.set_ylim(0.1, 1.0); A.axhline(0.5, color="gray", lw=.4)
        A.set_xticks(range(a, a + win + 1, 20)); A.tick_params(labelsize=6); A.grid(alpha=.3)
    ax[0].legend(loc="upper right", fontsize=7)
    plt.tight_layout(); plt.savefig(V2 / "signals-overview.png", dpi=70)
    print(V2 / "signals-overview.png")
