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
   |  POST v1/bridge/jobs/<id>/uploads       <-- recordings: name, bytes, sha256
   |  200 presigned PUT URL per file   ----->
   |                                       |  PUT <presigned url> ----------->  R2
   |  POST v1/bridge/jobs/<id>/report        <-- result, never the credential
   |  HEAD each key in R2, then
   |  200 {"delete": [names]}          ----->  bridge removes them from its spool
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
- Recordings do not use this endpoint. They go to object storage (next section).

### `POST v1/bridge/jobs/<job-id>/uploads`

Recordings go straight from the bridge to object storage (Cloudflare R2)
through presigned URLs. The bridge never holds storage credentials and never
chooses object keys. The backend never relays video bytes.

The bridge sends this request after the device work is done, in batches of
`--upload-batch` files (default 16). A URL is requested just before it is
used, so it does not expire while earlier recordings are still uploading.

```json
{ "bridge": "site-salon-01",
  "artifacts": [ { "name": "track-101_20261029T050000_00001.dav", "bytes": 262144040,
                   "sha256": "…", "content_type": "application/octet-stream" } ] }
```

Response `200`:

```json
{ "grants": [ { "name": "track-101_20261029T050000_00001.dav",
                "key": "recordings/site-salon-01/job-0001/track-101_20261029T050000_00001.dav",
                "method": "PUT", "url": "https://<account>.r2.cloudflarestorage.com/<bucket>/<key>?X-Amz-…",
                "headers": { "Content-Type": "application/octet-stream" },
                "expires_at": 1793736000 } ],
  "stored": [ { "name": "…", "key": "…" } ] }
```

- **`grants`**: one presigned URL per file. The backend chooses the key, for
  example `recordings/<bridge>/<job>/<name>`. Keep the expiry short (15–60 min).
- **`stored`**: files already in the bucket with the same size and SHA-256.
  The bridge marks them uploaded and sends nothing, which makes re-runs cheap.
- **`404`**: the backend has no object storage. Recordings stay in the spool
  and the job still succeeds.

**Upload rules on the bridge side:**
- Send exactly `method url` with the grant's `headers` and an explicit
  `Content-Length`. Presigned PUTs reject chunked bodies.
- Never send the bridge token to the storage URL.
- Stream the file from the spool, so memory use does not grow with file size.
- If the store refuses a URL (400/401/403, e.g. it expired), ask once more
  for that file alone, then give up on it.
- Any other failure (transport error, 5xx) marks the file failed. The file
  stays in the spool, and the job is reported `partial` with `error_code: "upload"`.

A single PUT is enough for current recordings (about 250 MB each). R2 caps a
single PUT at about 5 GB. Larger files would need presigned multipart uploads.

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
      "bytes": 262144040, "sha256": "…", "uploaded": true,
      "object_key": "recordings/site-salon-01/job-2026-11-02-0001/track-101_20261029T050000_00001.dav" }
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
| `upload` | Recordings were downloaded but some did not reach object storage. They stay in the spool. Re-issue the job: files already stored are skipped. |
| `unsupported` | Wrong family, or the job kind is not implemented yet (Ezviz). |
| `invalid_job` | The job is malformed or has an unsafe id. |
| `io` | Local disk problem on the bridge. |

**Report response.** `204`, or `200 {"delete": [names]}`. The backend
returns a name only after a HEAD on its key matches the reported size and
SHA-256. The bridge then deletes those files from its spool. It ignores any
name this report did not mark as uploaded, and any name that is not a plain
file name. Until the backend confirms, nothing is deleted.

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

- Real R2 signing in the gateway (boto3 `generate_presigned_url("put_object", …)`
  against the R2 S3 endpoint), plus a read URL for the agent once the job is done.
- Sign the `x-amz-checksum-sha256` header, so R2 itself rejects corrupted bytes.
  Check R2's support for this before relying on it.
- A re-issued job whose recordings are already stored still re-downloads them
  from the DVR, because the spool was cleaned. A "which of these are stored?"
  check before downloading would avoid that.
- A retry/resume job for uploads only (`partial` + `upload`), without re-running the device search.
- Job leases and timeouts. A job that is polled but never reported should go
  back to the queue.
- Bridge enrollment and token rotation.
- A per-device capability probe (see `reverse-notes.md`).
