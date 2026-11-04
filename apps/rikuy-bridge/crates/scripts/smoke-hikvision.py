#!/usr/bin/env python3
"""Exercise the real Hikvision CLI against a local mock DVR (no hardware)."""
import json
import os
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
MOCKS = ROOT.parent / "mocks"


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    # An explicit target directory works even when CARGO_TARGET_DIR is set.
    target = ROOT / "target"
    for manifest, binary in ((ROOT, "rikuy-bridge-hikvision"), (MOCKS, "mock-isapi")):
        subprocess.run([
            "cargo", "build", "--locked", "--manifest-path", str(manifest / "Cargo.toml"),
            "--target-dir", str(target), "--bin", binary,
        ], check=True)

    suffix = ".exe" if os.name == "nt" else ""
    bridge = target / "debug" / f"rikuy-bridge-hikvision{suffix}"
    mock = target / "debug" / f"mock-isapi{suffix}"
    # Port zero lets the OS choose a free port; never touch a real device.
    with tempfile.TemporaryDirectory(prefix="rikuy-smoke-") as tmp:
        work = Path(tmp)
        with subprocess.Popen(
            [str(mock), "127.0.0.1:0", "96"], stderr=subprocess.PIPE,
            stdout=subprocess.DEVNULL, text=True,
        ) as dvr:
            try:
                # The mock emits its address only after it has bound the listener.
                url = None
                for line in dvr.stderr:
                    if line.startswith("mock-isapi listening on "):
                        url = line.strip().split()[-1]
                        break
                check(url is not None, "Mock DVR did not start")
                env = dict(os.environ, RIKUY_DEVICE_USER="admin", RIKUY_DEVICE_PASSWORD="correct-horse")

                def run(command, *args, password="correct-horse", code=0):
                    result = subprocess.run(
                        [str(bridge), command, "--device", url, *map(str, args)],
                        env=dict(env, RIKUY_DEVICE_PASSWORD=password),
                        capture_output=True, text=True, timeout=30,
                    )
                    check(result.returncode == code, f"{command}: {result.stderr}")
                    check(password not in result.stdout + result.stderr, "Password leaked in CLI output")
                    return json.loads(result.stdout) if code == 0 else None

                cameras = run("list-cameras")
                check([c["id"] for c in cameras] == list(range(101, 802, 100)), "Unexpected cameras")
                shot = work / "cam3.jpg"
                run("screenshot", "--channel", 3, "--out", shot)
                jpeg = shot.read_bytes()
                check(jpeg.startswith(b"\xff\xd8") and jpeg.endswith(b"\xff\xd9"), "Invalid mock JPEG envelope")

                window = ("--from", "2026-10-29T05:00:00", "--to", "2026-10-30T05:00:00")
                recordings = run("search", *window)
                check(len(recordings) == 384, "Search did not traverse all pages")
                check(run("search", "--from", "2026-11-01T00:00:00", "--to", "2026-11-01T01:00:00") == [], "Expected empty history")

                download_args = (*window, "--track", 101, "--out", work / "recordings")
                first = run("download", *download_args)
                check(first["downloaded"] == 96, "Missing recordings")
                files = sorted((work / "recordings").glob("*.dav"))
                check(len(files) == 96, "Missing DAV files")
                check(all(p.read_bytes().startswith(b"IMKH") for p in files), "Missing IMKH wrapper")
                check(sum(p.stat().st_size for p in files) == first["bytes"], "Byte total mismatch")
                before = {p: p.read_bytes() for p in files}
                second = run("download", *download_args)
                check(second["downloaded"] == 0 and second["skipped_existing"] == 96, "Resume was not idempotent")
                check(all(p.read_bytes() == data for p, data in before.items()), "Resume changed recordings")

                run("list-cameras", password="deliberately-wrong", code=77)
                run("list-cameras")  # One rejected credential must not lock the account.
                print("PASS: 8 cameras, snapshot, 384 paginated results, empty history,")
                print("      96 downloads, byte-preserving resume, safe credential rejection.")
                print("Synthetic media only: JPEG is not decodable; DAV is not playable video.")
            finally:
                dvr.terminate()
                try:
                    dvr.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    dvr.kill()
                    dvr.wait()


if __name__ == "__main__":
    main()
