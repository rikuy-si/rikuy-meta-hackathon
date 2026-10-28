"""Gateway configuration.

Everything is constructor-injectable so tests build small worlds; `dev()`
gives a default local world (local object store, temp dirs) and `from_env()`
reads RIKUY_* variables for real runs.
"""

from __future__ import annotations

import secrets
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field


class R2Settings(BaseModel):
    bucket: str = "rikuy-recordings"
    endpoint: str = ""  # https://<account>.r2.cloudflarestorage.com
    access_key_id: str = ""
    secret_access_key: str = Field(default="", repr=False)
    presign_ttl_secs: int = 900
    read_ttl_secs: int = 3600


class Settings(BaseModel):
    store: Literal["local", "r2", "none"] = "local"
    r2: R2Settings = R2Settings()

    # Local stand-in store (tests, demos without cloud credentials).
    local_store_secret: str = Field(default="", repr=False)
    local_store_base: str = "http://127.0.0.1:8000"  # where bridges reach this app

    # Bridge-facing behavior.
    lease_secs: int = 300  # an unreported job goes back to the queue after this
    max_artifact_bytes: int = 64 * 1024 * 1024

    # Admin / actor auth.
    admin_token: str = Field(default="", repr=False)
    default_actor_token: str = Field(default="", repr=False)

    # Disk.
    artifacts_dir: Path = Path("artifacts")
    audit_path: Path = Path("audit.jsonl")

    # Device time zone used when a bridge has none registered (contract: UTC-5).
    default_device_tz: str = "America/Bogota"

    # How long MCP tools wait for a bridge report before giving up.
    tool_wait_secs: int = 120

    def ensure_dirs(self) -> None:
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)

    @classmethod
    def dev(cls, tmp: Optional[Path] = None, base: str = "http://127.0.0.1:8000") -> "Settings":
        tmp = tmp or Path(tempfile.mkdtemp(prefix="rikuy-gateway-"))
        return cls(
            store="local",
            local_store_secret=secrets.token_hex(16),
            local_store_base=base,
            admin_token="rikuy-admin-dev",
            default_actor_token="rikuy-actor-dev",
            artifacts_dir=tmp / "artifacts",
            audit_path=tmp / "audit.jsonl",
        )


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def expires(seconds: int) -> datetime:
    return now_utc() + timedelta(seconds=seconds)
