"""rikuy-gym: one subcommand per pipeline stage, all reading/writing a work dir.

    rikuy-gym timeline  --clips clips/ --work work/ [--concat]
    rikuy-gym detect    --clips clips/ --work work/            # RF-DETR + ByteTrack, 5 fps
    rikuy-gym segment   --clips clips/ --work work/ [--hd REC] # SAM 3 'person'
    rikuy-gym reconcile --work work/ --access access.csv --config gym.json
    rikuy-gym report    --work work/ --config gym.json         # muse-spark-1.3
    rikuy-gym build     --work work/ --config gym.json --out export/ --video-url URL
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import recordings


def _load(p: Path):
    return json.loads(p.read_text()) if p.exists() else None


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="rikuy-gym")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("timeline", "detect", "segment", "reconcile", "report", "build"):
        p = sub.add_parser(name)
        p.add_argument("--work", type=Path, required=True)
        if name in ("timeline", "detect", "segment"):
            p.add_argument("--clips", type=Path, required=True)
        if name in ("reconcile", "report", "build"):
            p.add_argument("--config", type=Path, required=True)
    sub.choices["timeline"].add_argument("--concat", action="store_true")
    sub.choices["detect"].add_argument("--fps", type=float, default=5.0)
    sub.choices["detect"].add_argument("--size", choices=["base", "large"], default="base")
    sub.choices["segment"].add_argument("--fps", type=float, default=2.0)
    sub.choices["segment"].add_argument("--hd", nargs="*", help="recordings for the 15 fps pass")
    sub.choices["reconcile"].add_argument("--access", type=Path, required=True)
    sub.choices["build"].add_argument("--out", type=Path, required=True)
    sub.choices["build"].add_argument("--video-url", required=True)
    a = ap.parse_args(argv)
    a.work.mkdir(parents=True, exist_ok=True)
    w = a.work
    cfg = _load(a.config) if getattr(a, "config", None) else None

    if a.cmd == "timeline":
        segs = recordings.timeline(a.clips)
        recordings.write(segs, w / "segments.json")
        if a.concat:
            recordings.concat(a.clips, segs, w / "review.mp4")
        print(f"{len(segs)} recordings, {sum(s.duration for s in segs):.0f} s")

    elif a.cmd == "detect":
        from . import detect

        detect.run(a.clips, recordings.read(w / "segments.json"), w / "tracks.json", a.fps, a.size)

    elif a.cmd == "segment":
        from . import segment

        segs = recordings.read(w / "segments.json")
        if a.hd:
            segment.run(a.clips, segs, w / "sam_hd.json", fps=15.0, hd=a.hd)
        else:
            segment.run(a.clips, segs, w / "sam.json", fps=a.fps)

    elif a.cmd == "reconcile":
        from .crossing import Line, crossings
        from .reconcile import read_access_log, reconcile

        line = Line(tuple(cfg["line"]["a"]), tuple(cfg["line"]["b"]), cfg["line"]["inside"])
        entries, exits = crossings(_load(w / "tracks.json"), recordings.read(w / "segments.json"), line)
        audit = reconcile(entries, exits, read_access_log(a.access), window=tuple(cfg["window"]),
                          validated=tuple(cfg["validated"]), clock_offset_s=cfg["clock_offset_s"],
                          tailgate_s=cfg.get("tailgate_s", 5.0))
        (w / "audit.json").write_text(json.dumps(audit, indent=1, ensure_ascii=False))
        s = audit["stats"]
        print(f"entries {s['entries']} exits {s['exits']} records {s['records']} "
              f"confirmed {s['confirmed']} phantom {s['phantom']} unrecorded {s['unrecorded']}")

    elif a.cmd == "report":
        from .report import ask

        audit = _load(w / "audit.json")
        audit["muse"] = ask(audit, cfg["question"])
        audit["muse"]["look"] = cfg.get("look", "")
        (w / "audit.json").write_text(json.dumps(audit, indent=1, ensure_ascii=False))
        print(audit["muse"]["answer"]["en"])

    elif a.cmd == "build":
        from .build import build

        path = build(a.out, _load(w / "audit.json"), _load(w / "segments.json"), _load(w / "tracks.json") or {},
                     _load(w / "sam.json") or {}, _load(w / "sam_hd.json"), video_url=a.video_url,
                     site=cfg.get("site", "[CLIENT]"), camera=cfg["camera"], line=cfg["line"],
                     sources=cfg["sources"], start_at=cfg.get("start_at"))
        print(f"open {path}")


if __name__ == "__main__":
    main()
