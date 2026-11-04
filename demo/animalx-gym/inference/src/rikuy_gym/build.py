"""Audit + overlays -> static web demo, from the skill's viewer template.

The demo is plain files (no server, works offline). The review video stays
private: ``video_url`` is a presigned R2 GET URL or a local path, never
committed.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parents[5] / "skills" / "gym-entrance-count" / "templates" / "viewer"


def js(var: str, obj) -> str:
    return f"window.{var}=" + json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + ";\n"


def build(out: Path, audit: dict, segs: list[dict], tracks: dict, sam: dict, sam_hd: dict | None, *,
          video_url: str, site: str, camera: str, line: dict, sources: dict, start_at: str | None = None,
          template: Path = TEMPLATE) -> Path:
    shutil.copytree(template, out, dirs_exist_ok=True)
    data = out / "audit" / "data"
    data.mkdir(parents=True, exist_ok=True)
    total = round(sum(s["duration"] for s in segs), 1)
    doc = {"site": site, "camera": camera, "date": audit["window"]["from"][:10], **audit,
           "sources": sources, "line": line,
           "video": {"file": video_url, "total": total, "segments": segs},
           "start_at": start_at or audit["window"]["from"]}
    doc["stats"]["video_covered_s"] = total
    (data / "audit.js").write_text(js("AUDIT", doc))
    (data / "overlay.js").write_text(js("OVERLAY", {"sam": sam, "local": tracks}))
    (data / "overlay_hd.js").write_text(js("OVERLAY_HD", sam_hd or {}))
    (out / "index.html").write_text('<!doctype html><meta charset="utf-8">'
                                    '<meta http-equiv="refresh" content="0; url=audit/index.html">'
                                    '<a href="audit/index.html">Open the audit</a>\n')
    return out / "index.html"
