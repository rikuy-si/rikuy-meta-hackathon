# Backend contract

This contract covers how the Rikuy backend (the FastMCP gateway) and a bridge
running on the customer's network talk to each other. The bridge only makes
outbound calls: it polls for work, executes it, and reports back. The backend
never connects to the bridge or to the devices.

```
backend                                bridge (customer LAN)                device
   |  GET  v1/bridge/jobs/next  <---------- poll (Bearer bridge token)
   |  200 job {device, credential, kind} -->
   |                                       |  ISAPI (Digest, plain HTTP) --->  DVR
   |                                       |  <--- XML / JPEG / .dav
   |  PUT  v1/bridge/jobs/<id>/artifacts/<name>  <-- small artifacts (snapshots)
   |  POST v1/bridge/jobs/<id>/report        <-- result, never the credential
```

## Authentication

- **Bridge to backend.** Every call sends `Authorization: Bearer <bridge token>`.
  The token identifies one bridge at one site and is issued at enrollment. It
  lives in a file only the service account can read, and it is not a device
  secret.
- A 401 or 403 from the backend stops the daemon with **exit 77**. The bridge
  does not keep polling with a token that was rejected.
- Device credentials never live on the bridge. They travel inside each job,
  over the same authenticated TLS channel.

## Endpoints

### `GET v1/bridge/jobs/next?bridge=<bridge-id>`

- **200** with one job (below), or **204** when the queue is empty.
- The bridge polls every `--poll-interval-ms` (default 5 s). If the backend is
  unavailable, it backs off exponentially up to 5 min.

### `POST v1/bridge/jobs/<job-id>/report`

The body is a Report (below). The backend should treat a report as final for that job id.

### `PUT v1/bridge/jobs/<job-id>/artifacts/<name>`

- Sends raw bytes with a `Content-Type` header (`image/jpeg` for snapshots).
- Snapshots are uploaded right away, so an agent can get a live image.
- Recordings are not uploaded through this endpoint. They stay in the bridge
  spool (`<spool>/<job-id>/`), and the report lists them with size and SHA-256.
  Moving them to object storage (R2) is the next step; see "Open items".

## Job

```json
{
  "id": "job-2026-11-02-0001",
  "device": { "family": "hikvision", "base_url": "http://10.0.0.20" },
  "credential": { "username": "admin", "password": "<device password>" },
  "kind": "download",
  "from": "2026-10-29T05:00:00",
  "to":   "2026-10-29T06:00:00",
  "tracks": [101]
}
```

| Field | Rules |
|---|---|
| `id` | `[A-Za-z0-9_-]{1,128}`. Any other id is reported `invalid_job` and never used as a path. |
| `device.family` | Must match the bridge binary (`hikvision`, `ezviz`). A mismatch is reported `unsupported`. |
| `device.base_url` | The device as seen from the bridge host. Hikvision uses `http://` only, because ISAPI on the LAN is plain HTTP. |
| `credential` | Held in memory for the job only and zeroized afterwards. Never logged, reported or written. |
| `kind` | `list_cameras` · `snapshot` (`channel`) · `search` (`from`, `to`, `tracks?`) · `download` (`from`, `to`, `tracks?`) |
| `from` / `to` | **Device-local wall-clock time**, with no zone. Hikvision recorders write local time with a misleading `Z` suffix, so the bridge never converts it as UTC. The backend must convert user requests into the device's local time. |
| `tracks` | Recording track ids (`101` = camera 1 main stream). Empty means every enabled track. |
| `channel` | Camera number, 1-based. Snapshots use the main stream (`<n>01`). |

## Report

```json
{
  "job_id": "job-2026-11-02-0001",
  "bridge": "site-salon-01",
  "family": "hikvision",
  "status": "succeeded",
  "artifacts": [
    { "kind": "recording", "name": "track-101_20261029T050000_00001.dav",
      "bytes": 262144040, "sha256": "…", "uploaded": false }
  ],
  "data": { "found": 4, "skipped_existing": 0 }
}
```

| `status` | Meaning |
|---|---|
| `succeeded` | Everything requested was produced. |
| `partial` | Some artifacts were produced before a fatal error. `error_code` says why. |
| `failed` | Nothing usable was produced. |
| `auth_rejected` | The device refused the credential. |

| `error_code` | Meaning, and what the backend should do |
|---|---|
| `auth_rejected` | Ask the owner for a new credential. **Do not re-send the same one**: the bridge refuses it locally anyway, so the device's lockout counter does not move. |
| `unreachable` | The device route is down. The bridge pauses before its next poll. Retry later. |
| `protocol` | The device answered with something unexpected, such as a missing IMKH wrapper or a size mismatch. |
| `unsupported` | Wrong family, or the job kind is not implemented yet (Ezviz). |
| `invalid_job` | The job is malformed or has an unsafe id. |
| `io` | Local disk problem on the bridge. |

`data`: `list_cameras` returns the tracks, `search` returns the recordings
(track, local start/end, playback URI, advertised size), and `download` returns counts.

## Artifacts

- **Recording.** A Hikvision `.dav` is the advertised payload plus a 40-byte
  `IMKH` wrapper (H.264 1280×720 + µ-law audio on the reference device). The
  bridge checks the magic number and the exact size before keeping a file. It
  writes to `.dav.part` and renames only after validation.
- Re-running a download job skips files that are already complete. The
  per-directory `manifest.json` is merged and written atomically, so
  overlapping runs do not drop each other's entries.

## Open items

- Recording delivery to object storage (presigned R2 PUT issued in the job, or
  a separate `upload` job kind).
- Job leases and timeouts. A job that is polled but never reported should go
  back to the queue.
- Bridge enrollment and token rotation.
- A per-device capability probe (see `reverse-notes.md`).
