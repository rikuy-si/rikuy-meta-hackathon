# rikuy-gateway

The FastMCP gateway: the single contract between AI agents and the camera
bridges on customer networks.

- **Bridge-facing REST API** (`v1/bridge/*`): job queue, reports, snapshot
  artifacts, presigned-URL upload grants. Implements
  `apps/rikuy-bridge/crates/docs/backend-contract.md` exactly.
- **Agent-facing MCP tools** (`list_cameras`, `live_image`, `download_history`,
  `upload_to_r2`) with per-actor grants, audit log and revocation.
- **Object storage**: Cloudflare R2 via presigned PUT/GET (boto3), or a local
  stand-in store for tests and demos without cloud credentials.

## Develop

```
uv venv && uv pip install -e '.[dev]'
pytest
uvicorn rikuy_gateway.app:app --factory   # see README run section
```

Work in progress; see the repository TODO.md for status.
