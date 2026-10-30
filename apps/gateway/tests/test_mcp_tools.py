"""MCP tools with grants: the agent-facing surface, tested in memory."""

import asyncio
import hashlib
import json
import threading
import time

import pytest

from rikuy_gateway.app import create_app
from rikuy_gateway.config import Settings
from rikuy_gateway.models import Artifact, Report
from rikuy_gateway.tz import to_device_local

BRIDGE = "site-salon-01"
TOKEN = "bridge-token-test"
ACTOR = "rikuy-actor-dev"


class FakeBridge:
    """Plays the bridge daemon: polls, executes, uploads, reports."""

    def __init__(self, app) -> None:
        self.gw = app.state.gateway
        self.jobs = []
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self):
        while not self._stop.is_set():
            job = self.gw.next_job(BRIDGE)
            if job is None:
                time.sleep(0.05)
                continue
            self.jobs.append(job)
            self._execute(job)

    def _execute(self, job):
        store = self.gw.objectstore
        artifacts, data = [], None
        if job.kind == "list_cameras":
            data = [{"id": 101, "name": "Entrance"}, {"id": 102, "name": "Till"}]
        elif job.kind == "snapshot":
            payload = b"\xff\xd8fake-jpeg-bytes"
            sha = hashlib.sha256(payload).hexdigest()
            self.gw.store_artifact(job.id, f"snapshot-cam{job.channel}.jpg", "image/jpeg", payload)
            artifacts = [Artifact(kind="snapshot", name=f"snapshot-cam{job.channel}.jpg", bytes=len(payload), sha256=sha, uploaded=True)]
        elif job.kind == "download":
            for i in range(2):
                payload = b"IMKH" + bytes([i]) * 500
                sha = hashlib.sha256(payload).hexdigest()
                name = f"track-101_{i:05d}.dav"
                key = f"recordings/{BRIDGE}/{job.id}/{name}"
                store.put(key, payload, "application/octet-stream")
                artifacts.append(
                    Artifact(kind="recording", name=name, bytes=len(payload), sha256=sha, uploaded=True, object_key=key)
                )
            data = {"found": 2}
        self.gw.record_report(
            Report(job_id=job.id, bridge=BRIDGE, family="hikvision", status="succeeded", artifacts=artifacts, data=data)
        )


@pytest.fixture()
def world(tmp_path):
    s = Settings.dev(tmp=tmp_path, base="http://testserver", tool_wait_secs=10)
    app = create_app(s)
    app.state.gateway.enroll_bridge(
        BRIDGE, TOKEN, family="hikvision", tz="America/Bogota",
        device_base_url="http://10.0.0.20", device_username="admin", device_password="correct-horse",
    )
    return app


@pytest.fixture()
def mcp(world):
    from rikuy_gateway.mcp import build_mcp

    return build_mcp(world.state.gateway, world.state.settings)


def call(mcp, tool, args):
    from fastmcp import Client

    async def go():
        async with Client(mcp) as c:
            return await c.call_tool(tool, args)

    try:
        res = asyncio.run(go())
    except Exception as e:  # fastmcp raises tool errors (GrantDenied, GatewayError, ...)
        return {"_error": str(e)}
    data = getattr(res, "data", None)
    if data is not None:
        return data if isinstance(data, dict) else json.loads(data) if isinstance(data, str) else data
    return json.loads(res.content[0].text)


def test_list_cameras_returns_tracks(mcp, world):
    fb = FakeBridge(world).start()
    try:
        out = call(mcp, "list_cameras", {"bridge": BRIDGE})
    finally:
        fb.stop()
    assert out["status"] == "succeeded" and out["count"] == 2
    assert out["cameras"][0]["id"] == 101
    assert out["error_code"] is None


def test_live_image_saves_a_hash_verified_snapshot(mcp, world):
    fb = FakeBridge(world).start()
    try:
        out = call(mcp, "live_image", {"bridge": BRIDGE, "channel": 2})
    finally:
        fb.stop()
    assert out["status"] == "succeeded"
    assert out["name"] == "snapshot-cam2.jpg"
    p = __import__("pathlib").Path(out["path"])
    assert p.exists() and p.read_bytes().startswith(b"\xff\xd8")
    assert out["sha256"] == hashlib.sha256(p.read_bytes()).hexdigest()
    assert "warning" not in out


def test_download_history_converts_time_and_returns_shareable_urls(mcp, world):
    fb = FakeBridge(world).start()
    try:
        out = call(
            mcp,
            "download_history",
            {"bridge": BRIDGE, "start": "2026-10-29T10:00:00+02:00", "end": "2026-10-29T11:00:00+02:00"},
        )
    finally:
        fb.stop()
    assert out["status"] == "succeeded" and len(out["recordings"]) == 2
    # +02:00 10:00 == 03:00 in Bogota: the job the bridge saw was device-local 03:00
    job = fb.jobs[0]
    assert job.from_.isoformat() == "2026-10-29T03:00:00" and job.from_.tzinfo is None
    for rec in out["recordings"]:
        assert rec["object_key"].startswith(f"recordings/{BRIDGE}/")
        assert rec["url"].startswith("http://testserver/__store/rikuy-recordings/")
        assert "X-Local-Signature=" in rec["url"]


def test_upload_to_r2_shares_a_snapshot(mcp, world):
    fb = FakeBridge(world).start()
    try:
        snap = call(mcp, "live_image", {"bridge": BRIDGE, "channel": 1})
        out = call(mcp, "upload_to_r2", {"bridge": BRIDGE, "job_id": snap["job_id"], "name": snap["name"]})
    finally:
        fb.stop()
    assert out["object_key"] == f"snapshots/{BRIDGE}/{snap['job_id']}/{snap['name']}"
    stored = world.state.gateway.objectstore.object(out["object_key"])
    assert stored[0].startswith(b"\xff\xd8")
    assert "X-Local-Signature=" in out["url"]


def test_default_actor_token_works_and_unknown_tokens_do_not(mcp, world):
    fb = FakeBridge(world).start()
    try:
        ok = call(mcp, "list_cameras", {"bridge": BRIDGE})  # demo grant via settings
        bad = call(mcp, "list_cameras", {"bridge": BRIDGE, "actor_token": "nope"})
    finally:
        fb.stop()
    assert ok["status"] == "succeeded"
    assert "unknown actor token" in bad["_error"]


def test_grant_scopes_and_revocation(mcp, world):
    gw = world.state.gateway
    snap_only = gw.grants.issue(actor="narrow", bridges=[BRIDGE], actions=["live_image"])
    fb = FakeBridge(world).start()
    try:
        ok = call(mcp, "live_image", {"bridge": BRIDGE, "channel": 1, "actor_token": snap_only.token})
        denied = call(mcp, "download_history", {"bridge": BRIDGE, "start": "2026-10-29T05:00:00", "end": "2026-10-29T06:00:00", "actor_token": snap_only.token})
        gw.grants.revoke(grant_id=snap_only.id)
        revoked = call(mcp, "live_image", {"bridge": BRIDGE, "channel": 1, "actor_token": snap_only.token})
    finally:
        fb.stop()
    assert ok["status"] == "succeeded"
    assert "does not allow" in denied["_error"]
    assert "revoked" in revoked["_error"]


def test_unknown_bridge_and_missing_device_fail_cleanly(mcp, world):
    out = call(mcp, "list_cameras", {"bridge": "ghost"})
    assert "not enrolled" in out["_error"]
    world.state.gateway.enroll_bridge("bare", "t-bare")  # no device registered
    out = call(mcp, "list_cameras", {"bridge": "bare"})
    assert "no registered device" in out["_error"]


def test_time_conversion_semantics():
    # Bogota is UTC-5 all year: an explicit -05:00 time maps to itself.
    assert to_device_local("2026-10-29T05:00:00-05:00", "America/Bogota").isoformat() == "2026-10-29T05:00:00"
    # A UTC time becomes local wall clock.
    assert to_device_local("2026-10-29T05:00:00Z", "America/Bogota").isoformat() == "2026-10-29T00:00:00"
    # A naive time is already device-local (pass-through, no double conversion).
    assert to_device_local("2026-10-29T05:00:00", "America/Bogota").isoformat() == "2026-10-29T05:00:00"


def test_every_tool_call_is_audited(mcp, world):
    fb = FakeBridge(world).start()
    try:
        call(mcp, "list_cameras", {"bridge": BRIDGE})
    finally:
        fb.stop()
    events = world.state.gateway.audit.find(action="tool_call")
    assert events and events[-1]["actor"] == "demo-agent"
    raw = world.state.settings.audit_path.read_text()
    assert "correct-horse" not in raw  # device password never reaches the audit log
