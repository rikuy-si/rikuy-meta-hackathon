"""Recorder clips -> segment timeline.

The DVR records on motion only, so a morning is a set of short clips named by
their camera start time (``20261029T055509.mp4``). Clips arrive from the
``rikuy-video`` skill (``download_history``), one file per recording.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

NAME = re.compile(r"(\d{8}T\d{6})\.mp4$")


@dataclass
class Segment:
    recording: str      # clip file name
    cam_start: str      # camera clock, ISO, seconds precision
    video_start: float  # offset inside the concatenated review video
    duration: float


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    return float(out)


def timeline(clips_dir: Path, duration=probe_duration) -> list[Segment]:
    clips = sorted(p for p in clips_dir.iterdir() if NAME.search(p.name))
    segs, t = [], 0.0
    for p in clips:
        start = datetime.strptime(NAME.search(p.name).group(1), "%Y%m%dT%H%M%S")
        d = round(duration(p), 2)
        segs.append(Segment(p.name, start.isoformat(), round(t, 2), d))
        t += d
    return segs


def concat(clips_dir: Path, segs: list[Segment], out: Path) -> None:
    """One review video for the viewer (kept private, uploaded to R2)."""
    lst = out.with_suffix(".txt")
    lst.write_text("".join(f"file '{(clips_dir / s.recording).resolve()}'\n" for s in segs))
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-an", "-movflags", "+faststart", str(out)],
        check=True,
    )
    lst.unlink()


def write(segs: list[Segment], path: Path) -> None:
    path.write_text(json.dumps([asdict(s) for s in segs], indent=1))


def read(path: Path) -> list[Segment]:
    return [Segment(**s) for s in json.loads(path.read_text())]
