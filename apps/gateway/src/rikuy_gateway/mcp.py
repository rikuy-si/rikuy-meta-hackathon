"""The agent-facing MCP tools.

`list_cameras` · `live_image` · `download_history` · `upload_to_r2`

Every call is grant-checked and audited. Tools submit a job to the bridge
queue, wait for its report, and return structured results: cameras, a saved
snapshot with its hash, recordings with their object keys and shareable read
URLs. Times passed by the agent are converted to the device's local time.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .config import Settings
from .grants import GrantDenied
from .models import Credential, Device, Job, Report
from .state import GatewayError, GatewayState
from .tz import to_device_local


def build_mcp(state: GatewayState, settings: Settings):
    from fastmcp import FastMCP

    mcp = FastMCP("rikuy-gateway")

    def _bridge(bridge_id: str):
        with state.lock:
            b = state.bridges.get(bridge_id)
        if b is None or b.revoked:
            raise GatewayError("unknown_bridge", f"bridge {bridge_id!r} is not enrolled")
        if not b.device_base_url:
            raise GatewayError("no_device", f"bridge {bridge_id!r} has no registered device")
        return b

    def _authorize(token: Optional[str], bridge_id: str, action: str, **detail):
        t = token or settings.default_actor_token
        g = state.grants.verify(t, bridge_id, action)  # raises GrantDenied
        state.audit.record("tool_call", tool=action, actor=g.actor, bridge=bridge_id, **detail)
        return g

    def _submit(b, kind: str, **extra) -> str:
        job = Job(
            id=state.new_job_id(),
            device=Device(family=b.family, base_url=b.device_base_url),
            credential=Credential(username=b.device_username, password=b.device_password),
            kind=kind,
            **extra,
        )
        state.submit(job, b.id)
        return job.id

    def _wait(job_id: str) -> Report:
        return state.wait_report(job_id, timeout_secs=settings.tool_wait_secs)

    @mcp.tool
    def list_cameras(bridge: str, actor_token: Optional[str] = None) -> dict:
        """List the cameras (recording tracks) a bridge can see.

        Returns each track id and its description, e.g. [{"id": 101, ...}].
        Use a track id as `tracks` in download_history.
        """
        b = _bridge(bridge)
        _authorize(actor_token, bridge, "list_cameras")
        job_id = _submit(b, "list_cameras")
        r = _wait(job_id)
        cameras = r.data or []
        return {
            "bridge": bridge,
            "job_id": job_id,
            "status": r.status,
            "count": len(cameras) if isinstance(cameras, list) else None,
            "cameras": cameras,
            "error_code": r.error_code,
        }

    @mcp.tool
    def live_image(bridge: str, channel: int, actor_token: Optional[str] = None) -> dict:
        """Capture a live JPEG snapshot from one camera channel (1-based).

        Returns the local file path, byte size and SHA-256 of the snapshot.
        The image is verified by hash when it lands on the gateway.
        """
        b = _bridge(bridge)
        _authorize(actor_token, bridge, "live_image", channel=channel)
        job_id = _submit(b, "snapshot", channel=channel)
        r = _wait(job_id)
        out: dict = {"bridge": bridge, "job_id": job_id, "channel": channel, "status": r.status, "error_code": r.error_code}
        for a in r.artifacts:
            stored = state.artifact(job_id, a.name)
            if stored is None:
                continue
            if stored.sha256 != a.sha256:
                out["warning"] = "snapshot hash mismatch between bridge report and stored bytes"
            path = Path(settings.artifacts_dir) / f"{job_id}_{a.name}"
            path.write_bytes(stored.data)
            out.update(
                {
                    "name": a.name,
                    "path": str(path),
                    "bytes": a.bytes,
                    "sha256": a.sha256,
                    "content_type": stored.content_type,
                }
            )
        return out

    @mcp.tool
    def download_history(
        bridge: str,
        start: str,
        end: str,
        tracks: Optional[list[int]] = None,
        actor_token: Optional[str] = None,
    ) -> dict:
        """Download recorded video from a bridge for a time range.

        `start`/`end` are ISO-8601 with offset (e.g. 2026-10-29T05:00:00-05:00);
        they are converted to the device's local time. `tracks` defaults to
        every enabled track (get ids from list_cameras). Recordings upload
        straight to object storage; each result carries its object key and a
        shareable read URL.
        """
        b = _bridge(bridge)
        _authorize(actor_token, bridge, "download_history", start=start, end=end, tracks=tracks)
        tz = b.tz or settings.default_device_tz
        job_id = _submit(
            b,
            "download",
            **{
                "from_": to_device_local(start, tz),
                "to": to_device_local(end, tz),
                "tracks": tracks or [],
            },
        )
        r = _wait(job_id)
        store = state.objectstore
        recordings = []
        for a in r.artifacts:
            entry = {
                "name": a.name,
                "bytes": a.bytes,
                "sha256": a.sha256,
                "uploaded": a.uploaded,
                "object_key": a.object_key,
            }
            if a.uploaded and a.object_key and store is not None:
                entry["url"] = store.presign_get(a.object_key, ttl=settings.r2.read_ttl_secs)
            recordings.append(entry)
        return {
            "bridge": bridge,
            "job_id": job_id,
            "status": r.status,
            "error_code": r.error_code,
            "recordings": recordings,
            "summary": r.data,
        }

    @mcp.tool
    def upload_to_r2(bridge: str, job_id: str, name: str, actor_token: Optional[str] = None) -> dict:
        """Push a gateway-held snapshot artifact to object storage.

        Use this after live_image to get a shareable URL: pass the job_id and
        the snapshot name it returned. Returns the object key and a read URL.
        """
        b = _bridge(bridge)
        _authorize(actor_token, bridge, "upload", job_id=job_id, name=name)
        stored = state.artifact(job_id, name)
        if stored is None:
            raise GatewayError("no_artifact", f"no artifact {name!r} for job {job_id!r}")
        store = state.objectstore
        if store is None:
            raise GatewayError("no_storage", "the gateway has no object storage configured")
        key = f"snapshots/{bridge}/{job_id}/{name}"
        store.put(key, stored.data, stored.content_type)
        state.audit.record("snapshot_uploaded", job=job_id, name=name, key=key)
        return {
            "bridge": bridge,
            "job_id": job_id,
            "name": name,
            "object_key": key,
            "bytes": len(stored.data),
            "sha256": stored.sha256,
            "url": store.presign_get(key, ttl=settings.r2.read_ttl_secs),
            "expires_in_secs": settings.r2.read_ttl_secs,
        }

    # GrantDenied and GatewayError reach the agent as tool errors (fastmcp
    # converts raised exceptions), which is exactly what we want: the agent
    # sees "grant does not allow 'download_history'" instead of a crash.

    return mcp
