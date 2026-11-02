# rikuy-bridge

Rust binaries that run on the customer's network, next to the cameras and
recorders, and connect them to Rikuy. The Rikuy backend decides what to fetch
and provisions the device credential per job. The bridge runs the job against
the device and reports back. It makes only outbound calls, so the customer
opens no inbound port.

| Crate | Binary | Status |
|---|---|---|
| `common/` | — | Shared contract: jobs, reports, credential envelope, liveness probe, backend client, daemon loop, `Connector` trait, presigned-URL uploader for recordings |
| `hikvision/` | `rikuy-bridge-hikvision` | Hikvision/HiLook DVR/NVR over ISAPI: cameras, live snapshot, recording search and download, daemon |
| `ezviz/` | `rikuy-bridge-ezviz` | Ezviz cameras over ONVIF: Profile T (Media2) live snapshot, Profile G search and replay to MP4 (ffmpeg behind a credential-holding RTSP proxy), daemon. Needs ffmpeg/ffprobe. |

## Hikvision commands

```
export RIKUY_DEVICE_PASSWORD=...        # or --password-stdin; never on argv
rikuy-bridge-hikvision list-cameras --device http://10.0.0.20
rikuy-bridge-hikvision screenshot   --device http://10.0.0.20 --channel 1 --out cam1.jpg
rikuy-bridge-hikvision search       --device http://10.0.0.20 --from 2026-10-29T05:00:00 --to 2026-10-29T06:00:00
rikuy-bridge-hikvision download     --device http://10.0.0.20 --from 2026-10-29T05:00:00 --to 2026-10-29T06:00:00 --track 101 --out recordings/
rikuy-bridge-hikvision daemon       --backend https://<backend> --token-file token --spool spool --bridge-id <site>
```

Times are device-local. Exit codes:

| Code | Meaning |
|---|---|
| 0 | ok |
| 64 | usage |
| 69 | device unreachable |
| 76 | protocol error |
| 77 | credential rejected (never retried, to avoid account lockout) |

## Docs

- `docs/backend-contract.md`: endpoints, job and report schemas, error codes, time semantics
- `docs/windows.md`: cross build with zig, deployment on the customer's Windows host
- `docs/reverse-notes.md`: what the iVMS-4200 client confirms about the ISAPI flow, and new leads

## Develop

```
cargo test                         # 49 tests; mocks (DVR, ONVIF camera, backend, R2 stand-in) come from ../mocks; needs ffmpeg/ffprobe
cargo build --release
./scripts/build-windows.sh         # x86_64-pc-windows-gnu .exe files
```
