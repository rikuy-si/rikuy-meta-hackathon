"""Append-only audit log: every security-relevant event, as JSONL.

One line per event, oldest first. Anything whose key smells like a secret
(password, credential, token) is redacted before it can reach disk.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from .config import now_utc

_REDACTED_KEYS = ("password", "credential", "secret")
_TOKEN_KEYS = ("token",)


def _redact(detail: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in detail.items():
        lk = k.lower()
        if any(r in lk for r in _REDACTED_KEYS):
            continue
        if any(t in lk for t in _TOKEN_KEYS) and isinstance(v, str) and len(v) > 8:
            out[k] = v[:8] + "…"
        else:
            out[k] = v
    return out


class AuditLog:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.events: list[dict[str, Any]] = []

    def record(self, action: str, **detail: Any) -> dict[str, Any]:
        event = {"ts": now_utc().isoformat(), "action": action, **_redact(detail)}
        with self._lock:
            self.events.append(event)
            with self._path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event, separators=(",", ":")) + "\n")
        return event

    def tail(self, n: int = 20) -> list[dict[str, Any]]:
        return self.events[-n:]

    def find(self, **detail) -> list[dict[str, Any]]:
        return [e for e in self.events if all(e.get(k) == v for k, v in detail.items())]
