"""In-memory gateway state: bridges, job queue with leases, reports, artifacts.

One process, one lock: right size for a hackathon gateway. The seams
(`submit`, `next_job`, `record_report`, `wait_report`) are what a Redis or
Postgres backend would replace; nothing else in the codebase touches the
collections directly.
"""

from __future__ import annotations

import hashlib
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from .audit import AuditLog
from .config import Settings, now_utc
from .models import Job, Report

_PLAIN_NAME = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")


def is_plain_name(name: str) -> bool:
    """Artifact names must be plain file names: never a path, never a traversal."""
    return bool(name) and not name.startswith(".") and all(c in _PLAIN_NAME for c in name)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass
class Bridge:
    id: str
    token: str
    family: str = "hikvision"
    tz: str = ""
    enrolled_at: datetime = field(default_factory=now_utc)
    revoked: bool = False

    def __repr__(self) -> str:  # tokens stay out of logs
        return f"Bridge(id={self.id!r}, family={self.family!r}, revoked={self.revoked})"


@dataclass
class Lease:
    job_id: str
    bridge: str
    expires_at: datetime


@dataclass
class StoredArtifact:
    name: str
    content_type: str
    data: bytes
    sha256: str


class GatewayError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _in(seconds: float) -> datetime:
    return now_utc() + timedelta(seconds=seconds)


class GatewayState:
    def __init__(self, settings: Settings, audit: AuditLog) -> None:
        self.settings = settings
        self.audit = audit
        self.lock = threading.RLock()
        self.bridges: dict[str, Bridge] = {}
        self._by_token: dict[str, str] = {}
        self.queues: dict[str, deque[Job]] = {}
        self.leases: dict[str, Lease] = {}
        self._leased_jobs: dict[str, Job] = {}
        self.reports: dict[str, Report] = {}
        self.artifacts: dict[tuple[str, str], StoredArtifact] = {}
        self._known_jobs: set[str] = set()

    # -- bridges -----------------------------------------------------------

    def enroll_bridge(self, bridge_id: str, token: str, family: str = "hikvision", tz: str = "") -> Bridge:
        if not bridge_id or not is_plain_name(bridge_id) or "." in bridge_id:
            raise GatewayError("invalid_bridge", "bridge id must be plain [A-Za-z0-9_-]")
        with self.lock:
            existing = self.bridges.get(bridge_id)
            if existing is not None:
                if existing.token != token:
                    raise GatewayError("bridge_exists", "bridge id already enrolled with another token")
                existing.family = family
                existing.tz = tz or existing.tz
                existing.revoked = False
                return existing
            b = Bridge(id=bridge_id, token=token, family=family, tz=tz)
            self.bridges[bridge_id] = b
            self._by_token[token] = bridge_id
            self.queues.setdefault(bridge_id, deque())
        self.audit.record("bridge_enrolled", bridge=bridge_id, family=family)
        return b

    def bridge_for_token(self, token: str) -> Optional[Bridge]:
        with self.lock:
            bridge_id = self._by_token.get(token)
            return self.bridges.get(bridge_id) if bridge_id else None

    def revoke_bridge(self, bridge_id: str) -> None:
        with self.lock:
            b = self.bridges.get(bridge_id)
            if b:
                b.revoked = True
        self.audit.record("bridge_revoked", bridge=bridge_id)

    # -- jobs --------------------------------------------------------------

    def submit(self, job: Job, bridge_id: str) -> Job:
        with self.lock:
            b = self.bridges.get(bridge_id)
            if b is None or b.revoked:
                raise GatewayError("unknown_bridge", f"bridge {bridge_id!r} is not enrolled")
            if job.device.family != b.family:
                raise GatewayError(
                    "family_mismatch",
                    f"bridge {bridge_id!r} serves {b.family}, job wants {job.device.family}",
                )
            if job.id in self._known_jobs:
                raise GatewayError("duplicate_job", f"job {job.id!r} was already submitted")
            self._known_jobs.add(job.id)
            self.queues.setdefault(bridge_id, deque()).append(job)
        self.audit.record("job_submitted", job=job.id, bridge=bridge_id, kind=job.kind)
        return job

    def _expire_leases(self) -> None:
        """A job that was polled but never reported goes back to the queue."""
        now = now_utc()
        expired = [job_id for job_id, l in self.leases.items() if l.expires_at <= now]
        for job_id in expired:
            lease = self.leases.pop(job_id)
            job = self._leased_jobs.pop(job_id)
            self.queues.setdefault(lease.bridge, deque()).appendleft(job)
            self.audit.record("lease_expired", job=lease.job_id, bridge=lease.bridge)

    def next_job(self, bridge_id: str) -> Optional[Job]:
        with self.lock:
            self._expire_leases()
            q = self.queues.get(bridge_id)
            if not q:
                return None
            job = q.popleft()
            self._leased_jobs[job.id] = job
            self.leases[job.id] = Lease(job_id=job.id, bridge=bridge_id, expires_at=_in(self.settings.lease_secs))
        self.audit.record("job_polled", job=job.id, bridge=bridge_id)
        return job

    # -- reports -----------------------------------------------------------

    def record_report(self, report: Report) -> None:
        with self.lock:
            self.leases.pop(report.job_id, None)
            self._leased_jobs.pop(report.job_id, None)
            self.reports[report.job_id] = report
        self.audit.record(
            "job_reported",
            job=report.job_id,
            bridge=report.bridge,
            status=report.status,
            error_code=report.error_code,
        )

    def wait_report(self, job_id: str, timeout_secs: float, poll_secs: float = 0.2) -> Report:
        deadline = time.monotonic() + timeout_secs
        while True:
            with self.lock:
                r = self.reports.get(job_id)
            if r is not None:
                return r
            if time.monotonic() >= deadline:
                raise GatewayError("timeout", f"no report for job {job_id!r} within {timeout_secs:.0f}s")
            time.sleep(poll_secs)

    # -- artifacts (snapshots land here; recordings go to object storage) ----

    def store_artifact(self, job_id: str, name: str, content_type: str, data: bytes) -> StoredArtifact:
        if len(data) > self.settings.max_artifact_bytes:
            raise GatewayError("too_large", "artifact exceeds the gateway size cap")
        a = StoredArtifact(name=name, content_type=content_type, data=data, sha256=sha256_hex(data))
        with self.lock:
            self.artifacts[(job_id, name)] = a
        self.audit.record("artifact_stored", job=job_id, name=name, bytes=len(data), sha256=a.sha256)
        return a

    def artifact(self, job_id: str, name: str) -> Optional[StoredArtifact]:
        with self.lock:
            return self.artifacts.get((job_id, name))
