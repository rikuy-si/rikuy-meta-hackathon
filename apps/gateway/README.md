# rikuy-gateway

The FastMCP gateway: the single contract between AI agents and the camera
bridges on customer networks. One process serves bridges (REST, outbound-only
from their side) and agents (MCP over streamable HTTP at `/mcp`).

```
agent ──MCP──> gateway ──REST──> bridge (customer LAN) ──ISAPI──> DVR/NVR
                  │                  │
                  │                  └── presigned PUT ──> Cloudflare R2
                  └── grants · audit log · revocation · job leases
```

Implements `apps/rikuy-bridge/crates/docs/backend-contract.md` exactly.

## MCP tools

| Tool | What it does |
|---|---|
| `list_cameras` | Recording tracks a bridge can see (ids for `download_history`). |
| `live_image` | Live JPEG from one channel; saved gateway-side, hash-verified. |
| `download_history` | Recordings for a time range; uploaded straight to R2 with shareable read URLs. |
| `upload_to_r2` | Push a gateway-held snapshot to object storage; returns a shareable URL. |

Every call is grant-checked (actor tokens scoped to bridges and actions, with
expiry and instant revocation) and audited. Times with an offset are converted
to the device's local time; the bridge only ever sees naive device-local times.

## Run

```
uv venv && uv pip install -e '.[dev]'
python -m rikuy_gateway          # http://127.0.0.1:8000, MCP at /mcp
```

Environment (see `rikuy_gateway/config.py`): `RIKUY_STORE` (`local` stand-in ·
`r2` · `none`), `RIKUY_ADMIN_TOKEN`, `RIKUY_ACTOR_TOKEN`, and for real R2
`RIKUY_R2_ENDPOINT` / `RIKUY_R2_BUCKET` / `RIKUY_R2_ACCESS_KEY_ID` /
`RIKUY_R2_SECRET_ACCESS_KEY`. Enroll bridges and issue actor grants through
`/v1/admin/*`; bridges poll `/v1/bridge/jobs/next` with their token.

## Test

```
pytest                # 32 unit/API/tool tests, no hardware needed
pytest tests/test_e2e_daemon.py   # + the real Rust bridge daemon against the
                                  # mock ISAPI DVR; builds it on demand
```

The e2e test is the whole architecture in one run: an agent calls
`live_image` and `download_history` through MCP, the real
`rikuy-bridge-hikvision` daemon polls the job, talks ISAPI to the mock DVR,
uploads recordings with presigned URLs, and the gateway verifies each object
(HEAD, size + SHA-256) before telling the bridge to clean its spool — with
the audit log catching every step and no credential ever touching disk.

The end-user agent skill that drives these tools lives in `skills/rikuy-video`
(workstream 5).
