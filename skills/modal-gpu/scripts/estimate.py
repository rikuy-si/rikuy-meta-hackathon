#!/usr/bin/env python3
"""Quote a Modal GPU step: ETA and USD with a +/-50 % band.

    estimate.py --model sam3-image --frames 9000 --gpu L4
    estimate.py --model rfdetr --seconds 4500 --sample-fps 5 --gpu L4 --fps 31.2   # measured
    estimate.py --model sam3-image --frames 9000 --compare                          # every GPU
Planning throughputs and prices mirror references/budget.md; keep both in sync.
"""
import argparse

PRICE_H = {"T4": 0.59, "L4": 0.80, "A10": 1.10, "L40S": 1.95, "A100": 2.50, "H100": 3.95}
FPS = {  # frames (or objects) per second, planning values
    "rfdetr":     {"T4": 12, "L4": 25, "A10": 30, "L40S": 50, "A100": 60, "H100": 90},
    "yolo":       {"T4": 80, "L4": 150, "A10": 170, "L40S": 250, "A100": 280, "H100": 350},
    "sam3-image": {"T4": 1.5, "L4": 3, "A10": 4, "L40S": 7, "A100": 8, "H100": 12},
    "sam3-video": {"T4": 2, "L4": 4, "A10": 5, "L40S": 9, "A100": 10, "H100": 15},
    "rtmpose":    {"T4": 40, "L4": 80, "A10": 90, "L40S": 140, "A100": 160, "H100": 220},
    "reid":       {"T4": 300, "L4": 600, "A10": 700, "L40S": 1100, "A100": 1300, "H100": 1800},
    "sam3d-body": {"L4": 0.5, "A10": 0.6, "L40S": 1.2, "A100": 1.4, "H100": 2},
    "hunyuan3d":  {"L40S": 1 / 90, "A100": 1 / 70, "H100": 1 / 45},
}
CONTAINER_H = 0.01   # CPU + RAM next to the GPU
COLD_START_S = 120


def quote(model, gpu, frames, fps=None):
    rate = fps or FPS[model].get(gpu)
    if not rate:
        return None
    secs = frames / rate + COLD_START_S
    usd = secs / 3600 * (PRICE_H[gpu] + CONTAINER_H)
    return secs, usd


def fmt(s):
    return f"{int(s // 3600)}h{int(s % 3600 // 60):02d}m" if s >= 3600 else f"{int(s // 60)}m{int(s % 60):02d}s"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, choices=FPS)
    ap.add_argument("--frames", type=float)
    ap.add_argument("--seconds", type=float, help="footage seconds (with --sample-fps)")
    ap.add_argument("--sample-fps", type=float, default=1.0)
    ap.add_argument("--gpu", default="L4", choices=PRICE_H)
    ap.add_argument("--fps", type=float, help="measured throughput from a calibration run")
    ap.add_argument("--compare", action="store_true")
    a = ap.parse_args()
    frames = a.frames if a.frames is not None else (a.seconds or 0) * a.sample_fps
    print(f"{a.model}: {frames:,.0f} frames" + (" (measured fps)" if a.fps else " (planning fps, +/-50 %)"))
    print(f"{'GPU':6} {'ETA':>9} {'USD':>8}   band")
    for gpu in (PRICE_H if a.compare else [a.gpu]):
        q = quote(a.model, gpu, frames, a.fps if gpu == a.gpu else None)
        if not q:
            print(f"{gpu:6} {'n/a':>9}"); continue
        secs, usd = q
        band = 0.25 if a.fps and gpu == a.gpu else 0.5
        print(f"{gpu:6} {fmt(secs):>9} {usd:8.2f}   {fmt(secs * (1 - band))}-{fmt(secs * (1 + band))}, "
              f"${usd * (1 - band):.2f}-{usd * (1 + band):.2f}")


if __name__ == "__main__":
    main()
