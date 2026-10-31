"""End to end: agent MCP tool -> gateway -> real Rust bridge daemon -> mock DVR
-> recordings in the stand-in object store -> verified spool cleanup.

The bridge side is the real `rikuy-bridge-hikvision` binary from
`apps/rikuy-bridge` (built on demand), the camera is the mock ISAPI DVR from
`apps/rikuy-bridge/mocks`, and only the object store is a stand-in. Swap the
device URL for a real DVR and nothing else changes.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from rikuy_gateway.app import create_app
from rikuy_gateway.config import Settings

BRIDGE_ID = "e2e-bridge"
BRIDGE_TOKEN = "bridge-token-e2e"
DEVICE_USER = "admin"
DEVICE_PASS = "correct-horse"  # the mock DVR's credential


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def repo_root() -> Path:
    env = os.environ.get("RIKUY_BRIDGE_ROOT")
    if env:
        return Path(env)
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "PLAN.md").exists() and (parent / "apps" / "rikuy-bridge").exists():
            return parent
    return None  # type: ignore[return-value]


def bin_path(root: Path, rel: str) -> Path:
    p = root / "apps" / "rikuy-bridge" / rel
    if not p.exists():
        subprocess.run(["cargo", "build", "--manifest-path", str(root / "apps" / "rikuy-bridge" / ("crates" if "crates" in rel else "mocks") / "Cargo.toml")], check=True)
    return p


@pytest.fixture(scope="module")
def root() -> Path:
    r = repo_root()
    if r is None or not (r / "apps" / "rikuy-bridge").exists():
        pytest.skip("apps/rikuy-bridge not found (set RIKUY_BRIDGE_ROOT)")
    return r


@pytest.fixture(scope="module")
def binaries(root):
    dvr = bin_path(root, "mocks/target/debug/mock-isapi")
    daemon = bin_path(root, "crates/target/debug/rikuy-bridge-hikvision")
    return dvr, daemon


def wait_port(port: int, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
            return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"nothing listening on 127.0.0.1:{port}")


class Stack:
    def __init__(self, binaries) -> None:
        self.dvr_bin, self.daemon_bin = binaries
        self.dvr_port, self.gw_port = free_port(), free_port()
        self.dvr: subprocess.Popen | None = None
        self.daemon: subprocess.Popen | None = None
        self.server = None

    def start_dvr(self, clips: int = 8) -> str:
        self.dvr = subprocess.Popen(
            [str(self.dvr_bin), f"127.0.0.1:{self.dvr_port}", str(clips)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        wait_port(self.dvr_port)
        return f"http://127.0.0.1:{self.dvr_port}"

    def start_gateway(self, tmp: Path):
        import uvicorn

        settings = Settings.dev(tmp=tmp, base=f"http://127.0.0.1:{self.gw_port}")
        settings.tool_wait_secs = 60
        self.app = create_app(settings)
        self.gw = self.app.state.gateway
        self.gw.enroll_bridge(
            BRIDGE_ID, BRIDGE_TOKEN, family="hikvision", tz="America/Bogota",
            device_base_url=f"http://127.0.0.1:{self.dvr_port}",
            device_username=DEVICE_USER, device_password=DEVICE_PASS,
        )
        cfg = uvicorn.Config(self.app, host="127.0.0.1", port=self.gw_port, log_level="warning")
        self.server = uvicorn.Server(cfg)
        threading.Thread(target=self.server.run, daemon=True).start()
        wait_port(self.gw_port)
        return self.app

    def run_daemon(self, spool: Path, exit_when_idle: bool = True) -> subprocess.Popen:
        token_file = spool / "token"
        token_file.write_text(f"{BRIDGE_TOKEN}\n")
        args = [
            str(self.daemon_bin), "daemon",
            "--backend", f"http://127.0.0.1:{self.gw_port}",
            "--token-file", str(token_file),
            "--spool", str(spool / "spool"),
            "--bridge-id", BRIDGE_ID,
            "--poll-interval-ms", "100",
            "--unreachable-backoff-ms", "100",
        ]
        if exit_when_idle:
            args.append("--exit-when-idle")
        return subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    def stop(self) -> None:
        for p in (self.daemon, self.dvr):
            if p and p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    p.kill()
        if self.server:
            self.server.should_exit = True


@pytest.fixture()
def stack(binaries, tmp_path):
    s = Stack(binaries)
    s.start_dvr()
    s.start_gateway(tmp_path)
    yield s
    s.stop()


def test_agent_gets_a_live_image_and_recordings_end_to_end(stack, tmp_path):
    from rikuy_gateway.mcp import build_mcp

    mcp = build_mcp(stack.gw, stack.app.state.settings)

    import asyncio

    from fastmcp import Client

    def call(tool, args):
        async def go():
            async with Client(mcp) as c:
                return await c.call_tool(tool, args)

        return asyncio.run(go()).data

    # A bridge daemon is live on the "customer network".
    stack.daemon = stack.run_daemon(tmp_path, exit_when_idle=False)
    time.sleep(0.5)  # let the first poll authenticate

    # The agent asks for a live image.
    snap = call("live_image", {"bridge": BRIDGE_ID, "channel": 2})
    assert snap["status"] == "succeeded", snap
    img = Path(snap["path"])
    assert img.read_bytes().startswith(b"\xff\xd8")

    # And for an hour of history (user time with offset -> device-local).
    hist = call(
        "download_history",
        {"bridge": BRIDGE_ID, "start": "2026-10-29T05:00:00-05:00", "end": "2026-10-29T06:00:00-05:00", "tracks": [101]},
    )
    assert hist["status"] == "succeeded", hist
    assert len(hist["recordings"]) == 4  # the mock DVR's 15-minute clips
    for rec in hist["recordings"]:
        assert rec["uploaded"] is True and rec["object_key"]

    # The shareable read URLs actually serve bytes, over real HTTP.
    import httpx

    with httpx.Client(timeout=10) as http:
        r = http.get(hist["recordings"][0]["url"])
        assert r.status_code == 200
        assert r.content.startswith(b"IMKH") and len(r.content) == hist["recordings"][0]["bytes"]

    # Snapshots can be pushed to object storage and shared too.
    shared = call("upload_to_r2", {"bridge": BRIDGE_ID, "job_id": snap["job_id"], "name": snap["name"]})
    assert shared["url"].startswith(f"http://127.0.0.1:{stack.gw_port}/__store/")
    with httpx.Client(timeout=10) as http:
        assert http.get(shared["url"]).content.startswith(b"\xff\xd8")

    # The gateway verified every upload before freeing the bridge's spool.
    spool = tmp_path / "spool"
    dav_files = list(spool.rglob("*.dav"))
    assert dav_files == [], "the bridge spool should be empty after verified uploads"

    # And the whole flow is in the audit log.
    actions = [e["action"] for e in stack.gw.audit.events]
    for expected in ("bridge_enrolled", "job_submitted", "job_polled", "upload_grants", "job_reported", "tool_call", "spool_delete_ok"):
        assert expected in actions, f"missing audit action {expected!r}"
    raw = stack.app.state.settings.audit_path.read_text()
    assert DEVICE_PASS not in raw and BRIDGE_TOKEN not in raw


def test_queued_jobs_run_to_completion_with_exit_when_idle(stack, tmp_path):
    from rikuy_gateway.models import Credential, Device, Job

    gw = stack.gw
    device = Device(family="hikvision", base_url=f"http://127.0.0.1:{stack.dvr_port}")
    cred = Credential(username=DEVICE_USER, password=DEVICE_PASS)
    gw.submit(
        Job(id="e2e-cameras", device=device, credential=cred, kind="list_cameras"), BRIDGE_ID
    )
    gw.submit(
        Job(
            id="e2e-snap", device=device, credential=cred, kind="snapshot", channel=1,
        ),
        BRIDGE_ID,
    )
    stack.daemon = stack.run_daemon(tmp_path, exit_when_idle=True)
    out, _ = stack.daemon.communicate(timeout=120)
    assert stack.daemon.returncode == 0, out.decode()

    cameras = gw.reports["e2e-cameras"]
    assert cameras.status == "succeeded" and len(cameras.data) == 8
    snap = gw.reports["e2e-snap"]
    assert snap.status == "succeeded"
    stored = gw.artifact("e2e-snap", "snapshot-cam1.jpg")
    assert stored.data.startswith(b"\xff\xd8")
    assert stored.sha256 == snap.artifacts[0].sha256
