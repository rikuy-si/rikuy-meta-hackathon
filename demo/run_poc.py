"""One rehearsed agent run: skills → MCP → Ezviz bridge → mock camera → object store.

Writes demo/artifacts/: a real JPEG, a trimmed MP4 from the camera, and a
transcript with no credentials. The submission video is built from that MP4.

    apps/gateway/.venv/bin/python demo/run_poc.py
"""

from __future__ import annotations

import asyncio
import json
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path

import uvicorn

from rikuy_gateway.app import create_app
from rikuy_gateway.config import Settings
from rikuy_gateway.mcp import build_mcp

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "apps" / "rikuy-bridge"
OUT = ROOT / "demo" / "artifacts"
BRIDGE_ID = "demo-door"
BRIDGE_TOKEN = "bridge-token-demo"
DEVICE_USER = "admin"
DEVICE_PASS = "ABCDEF"


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def wait_port(port: int, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
            return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"nothing listening on 127.0.0.1:{port}")


def call(mcp, tool: str, args: dict):
    from fastmcp import Client

    async def go():
        async with Client(mcp) as c:
            return await c.call_tool(tool, args)

    return asyncio.run(go()).data


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["cargo", "build", "-q", "--manifest-path", str(BRIDGE / "mocks/Cargo.toml"), "--bin", "mock-onvif"],
        check=True,
    )
    subprocess.run(
        ["cargo", "build", "-q", "--manifest-path", str(BRIDGE / "crates/Cargo.toml"), "-p", "rikuy-bridge-ezviz"],
        check=True,
    )
    cam_bin = BRIDGE / "mocks/target/debug/mock-onvif"
    bridge_bin = BRIDGE / "crates/target/debug/rikuy-bridge-ezviz"

    http_port, rtsp_port, gw_port = free_port(), free_port(), free_port()
    work = OUT / ".run"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir()

    cam = subprocess.Popen(
        [str(cam_bin), f"127.0.0.1:{http_port}", f"127.0.0.1:{rtsp_port}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    daemon = None
    server = None
    try:
        wait_port(http_port)
        settings = Settings.dev(tmp=work, base=f"http://127.0.0.1:{gw_port}")
        settings.tool_wait_secs = 90
        app = create_app(settings)
        gw = app.state.gateway
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

        token = work / "token"
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
                str(work / "spool"),
                "--bridge-id",
                BRIDGE_ID,
                "--poll-interval-ms",
                "100",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(0.5)
        mcp = build_mcp(gw, app.state.settings)

        cameras = call(mcp, "list_cameras", {"bridge": BRIDGE_ID})
        snap = call(mcp, "live_image", {"bridge": BRIDGE_ID, "channel": 1})
        if snap.get("status") != "succeeded":
            raise SystemExit(f"live_image failed: {snap}")
        jpeg = Path(snap["path"]).read_bytes()
        if jpeg[:2] != b"\xff\xd8":
            raise SystemExit("live image is not a JPEG")
        (OUT / "door.jpg").write_bytes(jpeg)
        shared = call(
            mcp,
            "upload_to_r2",
            {"bridge": BRIDGE_ID, "job_id": snap["job_id"], "name": snap["name"]},
        )

        start, end = "2026-10-30T10:28:00-04:00", "2026-10-30T10:37:00-04:00"
        hist = call(
            mcp,
            "download_history",
            {"bridge": BRIDGE_ID, "start": start, "end": end, "tracks": [1]},
        )
        if hist.get("status") != "succeeded":
            raise SystemExit(f"download_history failed: {hist}")

        import httpx

        clip_saved = None
        recordings = []
        with httpx.Client(timeout=30) as http:
            snap_body = http.get(shared["url"]).content
            if snap_body[:2] != b"\xff\xd8":
                raise SystemExit("shareable snapshot URL did not serve the JPEG")
            for rec in hist["recordings"]:
                body = http.get(rec["url"]).content
                recordings.append(
                    {
                        "name": rec["name"],
                        "bytes": rec["bytes"],
                        "sha256": rec["sha256"],
                        "uploaded": rec["uploaded"],
                        "served_bytes": len(body),
                    }
                )
                if clip_saved is None and body[4:8] == b"ftyp":
                    raw = OUT / "door-clip.mp4"
                    raw.write_bytes(body)
                    clip_saved = raw.name

        transcript = {
            "scenario": "package-at-the-door",
            "skill": "skills/package-at-door",
            "bridge": BRIDGE_ID,
            "family": "ezviz",
            "cameras": cameras.get("count"),
            "live_image": {
                "status": snap["status"],
                "channel": 1,
                "bytes": snap["bytes"],
                "sha256": snap["sha256"],
                "shared": True,
            },
            "history": {"start": start, "end": end, "tracks": [1], "recordings": recordings},
            "clip": clip_saved,
            "snapshot": "door.jpg",
            "audit_actions": sorted({e["action"] for e in gw.audit.events}),
        }
        (OUT / "transcript.json").write_text(json.dumps(transcript, indent=2) + "\n")
        print(json.dumps({"snapshot": "door.jpg", "clip": clip_saved, "recordings": len(recordings)}))
    finally:
        for p in (daemon, cam):
            if p is not None and p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    p.kill()
        if server is not None:
            server.should_exit = True
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
