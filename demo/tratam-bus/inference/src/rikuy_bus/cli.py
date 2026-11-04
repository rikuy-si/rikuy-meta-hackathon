"""rikuy-bus: cabin camera vs. fare counter.

    rikuy-bus segment   --clip cabin.mp4 --start 2026-11-01T06:52:17 --work work/   # SAM 3, 15 fps
    rikuy-bus count     --work work/ [--zone x,y x,y ...]                            # occupancy, 2 fps
    rikuy-bus boardings --work work/                                                # candidates to review
    rikuy-bus build     --work work/ --fare-counter 7 --out export/ [--video-url URL]
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from . import boardings, occupancy

VIEWER = Path(__file__).resolve().parents[3] / "export"


def _zone(pairs):
    return [tuple(float(v) for v in p.split(",")) for p in pairs] if pairs else None


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="rikuy-bus")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("segment"); s.add_argument("--clip", type=Path, required=True)
    s.add_argument("--start", required=True); s.add_argument("--work", type=Path, required=True)
    s.add_argument("--fps", type=float, default=15.0)
    c = sub.add_parser("count"); c.add_argument("--work", type=Path, required=True); c.add_argument("--zone", nargs="*")
    b = sub.add_parser("boardings"); b.add_argument("--work", type=Path, required=True)
    b.add_argument("--hold", type=float, default=2.0)
    o = sub.add_parser("build"); o.add_argument("--work", type=Path, required=True)
    o.add_argument("--fare-counter", type=int, required=True); o.add_argument("--out", type=Path, required=True)
    o.add_argument("--video-url", default="")
    a = ap.parse_args(argv)
    a.work.mkdir(parents=True, exist_ok=True)

    if a.cmd == "segment":  # reuse the gym pipeline's SAM 3 stage
        from rikuy_gym.detect import iter_frames
        from rikuy_gym.segment import load_processor, segment_frame

        proc = load_processor()
        frames = [segment_frame(proc, f, "person", 1000.0, 0.5) for _, f in iter_frames(a.clip, a.fps)]
        meta = {"start": a.start, "duration": len(frames) / a.fps, "fps": a.fps}
        (a.work / "sam.json").write_text(json.dumps({"fps": a.fps, "scale": 1000, "frames": frames}))
        (a.work / "meta.json").write_text(json.dumps(meta))
    elif a.cmd == "count":
        sam = json.loads((a.work / "sam.json").read_text())
        (a.work / "occupancy.json").write_text(json.dumps(occupancy.series(sam, zone=_zone(a.zone))))
    elif a.cmd == "boardings":
        occ = json.loads((a.work / "occupancy.json").read_text())
        cands = boardings.candidates(occ, hold_s=a.hold)
        (a.work / "boardings.json").write_text(json.dumps(cands, indent=1))
        print(f"{len(cands)} candidates; review each clip and set status to boarded or rejected")
    else:
        sam = json.loads((a.work / "sam.json").read_text())
        meta = json.loads((a.work / "meta.json").read_text())
        occ = json.loads((a.work / "occupancy.json").read_text())
        bs = json.loads((a.work / "boardings.json").read_text())
        frames = len(sam["frames"])
        bus = {"video": {"file": a.video_url, "duration": round(meta["duration"], 2), "fps": sam["fps"]},
               "start": meta["start"], "speed_kmh": 0, "fare_counter": a.fare_counter, "sam": sam,
               "occupancy": occ, "boardings": [{k: x[k] for k in ("id", "t0", "t1", "status")} for x in bs],
               "cost": {"frames": frames, "usd": round(frames * 0.0002, 2)}}
        shutil.copytree(VIEWER, a.out, dirs_exist_ok=True)
        (a.out / "audit/data/bus.js").write_text("window.BUS=" + json.dumps(bus, separators=(",", ":")) + ";\n")
        print(json.dumps(boardings.reconcile(bs, a.fare_counter)))


if __name__ == "__main__":
    main()
