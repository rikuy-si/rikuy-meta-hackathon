"""End to end with the Ezviz/ONVIF bridge:

agent MCP tool -> gateway -> real rikuy-bridge-ezviz daemon -> mock Ezviz
ONVIF camera -> MP4 recordings in the stand-in object store -> shareable URLs.
"""

from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import threading
import time
from pathlib import Path

import httpx
import pytest

from rikuy_gateway.app import create_app
from rikuy_gateway.config import Settings

BRIDGE_ID = "tejiendo-ezviz"
BRIDGE_TOKEN = "bridge-token-ezviz-e2e"
DEVICE_USER = "admin"
DEVICE_PASS = "ABCDEF"  # the mock camera's verification code


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def wait_port(port: int, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
            return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"nothing listening on 127.0.0.1:{port}")


def repo_root() -> Path:
    env = os.environ.get("RIKUY_BRIDGE_ROOT")
    if env:
        return Path(env)
    for parent in Path(__file__).resolve().parents:
        if (parent / "PLAN.md").exists() and (parent / "apps" / "rikuy-bridge").exists():
            return parent
    raise RuntimeError("repo root not found")


@pytest.fixture(scope="module")
def binaries():
    bridge = repo_root() / "apps" / "rikuy-bridge"
    subprocess.run(
        ["cargo", "build", "-q", "--manifest-path", str(bridge / "mocks/Cargo.toml"), "--bin", "mock-onvif"],
        check=True,
    )
    subprocess.run(
        ["cargo", "build", "-q", "--manifest-path", str(bridge / "crates/Cargo.toml"), "-p", "rikuy-bridge-ezviz"],
        check=True,
    )
    return bridge / "mocks/target/debug/mock-onvif", bridge / "crates/target/debug/rikuy-bridge-ezviz"


@pytest.fixture()
def stack(binaries, tmp_path):
    cam_bin, bridge_bin = binaries
    http_port, rtsp_port, gw_port = free_port(), free_port(), free_port()
    cam = subprocess.Popen(
        [str(cam_bin), f"127.0.0.1:{http_port}", f"127.0.0.1:{rtsp_port}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    wait_port(http_port)

    import uvicorn

    settings = Settings.dev(tmp=tmp_path, base=f"http://127.0.0.1:{gw_port}")
    settings.tool_wait_secs = 90
    app = create_app(settings)
    gw = app.state.gateway
    # The gateway converts agent times to device-local with this zone; the
    # bridge then converts device-local to UTC with the camera's own TZ rules.
    gw.enroll_bridge(
        BRIDGE_ID,
        BRIDGE_TOKEN,
        family="ezviz",
        tz="America/New_York",
        device_base_url=f"http://127.0.0.1:{http_port}",
        device_username=DEVICE_USER,
        device_password=DEVICE_PASS,
    )
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=gw_port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    wait_port(gw_port)

    token = tmp_path / "token"
    token.write_text(BRIDGE_TOKEN)
    daemon = subprocess.Popen(
        [
            str(bridge_bin),
            "daemon",
            "--backend",
            f"http://127.0.0.1:{gw_port}",
            "--token-file",
            str(token),
            "--spool",
            str(tmp_path / "spool"),
            "--bridge-id",
            BRIDGE_ID,
            "--poll-interval-ms",
            "100",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    time.sleep(0.5)
    yield app, gw, tmp_path, daemon
    for p in (daemon, cam):
        p.terminate()
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
    server.should_exit = True


def test_agent_live_image_and_history_through_ezviz_onvif(stack):
    app, gw, tmp_path, daemon = stack
    from fastmcp import Client

    from rikuy_gateway.mcp import build_mcp

    mcp = build_mcp(gw, app.state.settings)

    def call(tool, args):
        async def go():
            async with Client(mcp) as c:
                return await c.call_tool(tool, args)

        return asyncio.run(go()).data

    cams = call("list_cameras", {"bridge": BRIDGE_ID})
    assert cams["status"] == "succeeded", cams
    assert cams["count"] == 2
    assert cams["cameras"][0]["encoding"] == "H265"

    snap = call("live_image", {"bridge": BRIDGE_ID, "channel": 1})
    assert snap["status"] == "succeeded", snap
    assert Path(snap["path"]).read_bytes()[:2] == b"\xff\xd8"

    # 10:28-10:37 New York time on Oct 30 (EDT). The camera has a gap at
    # 14:30-14:35 UTC, so exactly two clips come back.
    hist = call(
        "download_history",
        {
            "bridge": BRIDGE_ID,
            "start": "2026-10-30T10:28:00-04:00",
            "end": "2026-10-30T10:37:00-04:00",
            "tracks": [1],
        },
    )
    assert hist["status"] == "succeeded", hist
    names = [r["name"] for r in hist["recordings"]]
    assert names == ["cam1_20261030T102800_120s.mp4", "cam1_20261030T103500_120s.mp4"], hist

    with httpx.Client(timeout=30) as http:
        for rec in hist["recordings"]:
            assert rec["uploaded"] is True and rec["object_key"]
            body = http.get(rec["url"]).content
            assert len(body) == rec["bytes"] and body[4:8] == b"ftyp", "shareable URL serves the MP4"
            out = tmp_path / rec["name"]
            out.write_bytes(body)
            probe = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "stream=codec_name",
                    "-of",
                    "csv=p=0",
                    str(out),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            assert probe.stdout.split() == ["hevc", "aac"]

    shared = call("upload_to_r2", {"bridge": BRIDGE_ID, "job_id": snap["job_id"], "name": snap["name"]})
    with httpx.Client(timeout=10) as http:
        assert http.get(shared["url"]).content[:2] == b"\xff\xd8"

    assert list((tmp_path / "spool").rglob("*.mp4")) == [], "verified recordings must leave the spool"
    actions = {e["action"] for e in gw.audit.events}
    for a in ("bridge_enrolled", "tool_call", "job_reported", "upload_grants", "spool_delete_ok"):
        assert a in actions, a
    raw = app.state.settings.audit_path.read_text()
    assert DEVICE_PASS not in raw and BRIDGE_TOKEN not in raw
    daemon.poll()
