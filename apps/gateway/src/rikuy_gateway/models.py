"""Contract types for jobs and reports.

These mirror `apps/rikuy-bridge/crates/docs/backend-contract.md` exactly; the
bridge (Rust) validates the same rules on its side, so a job the gateway
accepts is a job the bridge will run, and a report the bridge sends is a
report the gateway can trust.

Time semantics: `from`/`to` in a Job are **device-local wall-clock times with
no zone**. Hikvision recorders write local time with a misleading `Z` suffix,
so the bridge never converts. The gateway converts user-facing times (which
carry an offset) into the device's local time before building a job.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

JOB_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

JobKind = Literal["list_cameras", "snapshot", "search", "download"]
Family = Literal["hikvision", "ezviz"]
ReportStatus = Literal["succeeded", "partial", "failed", "auth_rejected"]

#: What the backend should do for each report error code (backend-contract.md).
ERROR_CODE_ACTION = {
    "auth_rejected": "ask the owner for a new credential; never re-send the same one",
    "unreachable": "the device route is down; retry later",
    "protocol": "the device answered something unexpected",
    "upload": "recordings are in the spool; re-issue the job, stored files are skipped",
    "unsupported": "wrong family, or the kind is not implemented for it",
    "invalid_job": "the job was malformed or had an unsafe id",
    "io": "local disk problem on the bridge",
}


class Device(BaseModel):
    """The device as seen from the bridge host."""

    family: Family
    base_url: str

    @model_validator(mode="after")
    def _check_url(self) -> "Device":
        if not self.base_url.startswith(("http://", "https://")):
            raise ValueError("device.base_url must be an http(s) URL")
        if self.family == "hikvision" and not self.base_url.startswith("http://"):
            # ISAPI on the customer LAN is plain HTTP (backend-contract.md).
            raise ValueError("hikvision devices use http:// only")
        return self


class Credential(BaseModel):
    """Device credential. Travels inside one job only; never logged or stored."""

    username: str
    password: str = Field(repr=False)

    def __str__(self) -> str:  # keep it out of logs and tracebacks
        return f"Credential(username={self.username!r}, password=***)"


class Job(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")
    device: Device
    credential: Credential
    kind: JobKind
    from_: Optional[datetime] = Field(default=None, alias="from")
    to: Optional[datetime] = None
    tracks: list[int] = Field(default_factory=list)
    channel: Optional[int] = None

    model_config = {"populate_by_name": True}

    @field_validator("id")
    @classmethod
    def _safe_id(cls, v: str) -> str:
        if not JOB_ID_RE.match(v):
            raise ValueError("job id must match [A-Za-z0-9_-]{1,128}")
        return v

    @model_validator(mode="after")
    def _check_kind_fields(self) -> "Job":
        if self.from_ is not None and self.from_.tzinfo is not None:
            raise ValueError("job times are device-local and must be naive; convert upstream")
        if self.to is not None and self.to.tzinfo is not None:
            raise ValueError("job times are device-local and must be naive; convert upstream")
        if self.kind == "snapshot" and (self.channel is None or self.channel < 1):
            raise ValueError("snapshot requires a 1-based channel")
        if self.kind in ("search", "download"):
            if self.from_ is None or self.to is None:
                raise ValueError(f"{self.kind} requires from and to")
            if self.to <= self.from_:
                raise ValueError("to must be after from")
        if any(t < 1 for t in self.tracks):
            raise ValueError("tracks must be positive ids")
        return self

    def wire(self) -> dict[str, Any]:
        """The exact JSON the bridge expects (aliases, no nulls)."""
        return self.model_dump(by_alias=True, exclude_none=True, mode="json")


class Artifact(BaseModel):
    kind: Literal["snapshot", "recording"]
    name: str
    bytes: int
    sha256: str
    uploaded: bool = False
    object_key: Optional[str] = None


class Report(BaseModel):
    job_id: str
    bridge: str
    family: Family
    status: ReportStatus
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    artifacts: list[Artifact] = Field(default_factory=list)
    data: Optional[Any] = None


class UploadRequestItem(BaseModel):
    name: str
    bytes: int
    sha256: str
    content_type: str = "application/octet-stream"


class UploadRequest(BaseModel):
    bridge: str
    artifacts: list[UploadRequestItem]
