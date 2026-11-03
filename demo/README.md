# POC

One rehearsed run of `skills/package-at-door` against the mock Ezviz camera. No customer device was contacted.

| File | What it is |
|---|---|
| `poc.mp4` | 14-second cut: title, the first 6 seconds of the recording the agent downloaded, then the live JPEG. |
| `artifacts/door.jpg` | The JPEG `live_image` returned (640×360). |
| `artifacts/transcript.json` | Tool results. No credential, token, or signed URL. |

The run listed 2 cameras, stored the snapshot, downloaded the 10:28–10:37 New York window on 2026-10-30 as two MP4s, and the audit log contains `tool_call`, `upload_grants`, and `spool_delete_ok`.

Replay:

```
apps/gateway/.venv/bin/python demo/run_poc.py
```

Needs ffmpeg and ffprobe on `PATH`. The script rebuilds `mock-onvif` and `rikuy-bridge-ezviz` if necessary.

## Submission checklist

Deadline: **Nov 4, 2026, 5:00 pm (UTC-5).**

- Repository: `https://github.com/rikuy-si/rikuy-meta-hackathon`
- Video: `demo/poc.mp4`
- Still: `demo/artifacts/door.jpg`
- Blurb: Rikuy Connect lets an agent ask for a live image or a historical clip. A FastMCP gateway checks a grant, audits the call, and hands the job to a Rust bridge on the customer network (Hikvision ISAPI or Ezviz ONVIF). Recordings go to object storage through presigned URLs and the agent gets a shareable link back.

The form on the hackathon site is filled by hand. This repo does not submit it.
