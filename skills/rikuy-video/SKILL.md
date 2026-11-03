---
name: rikuy-video
description: Live snapshot or historical recording from a Rikuy camera bridge, returned as a shareable URL. Use when the user asks for a live image, a clip from a time range, or a link to footage.
---

# Rikuy video

The gateway MCP server exposes four tools: `list_cameras`, `live_image`, `download_history`, `upload_to_r2`. Call them on the gateway's `/mcp` endpoint. Leave `actor_token` unset unless the user handed you one.

You need a bridge id before any call. Take it from the user. If they did not name one, ask once and stop until they answer.

## Live image

1. Call `live_image` with the bridge id and a 1-based `channel`.
2. Done when `status` is `succeeded` and the result has `path`, `sha256`, and `job_id`. On any other status, tell the user `error_code` and stop.
3. Call `upload_to_r2` with that `job_id` and `name`.
4. Done when the result has `url`. Give the user that URL, the channel, and the byte size.

## Historical clip

1. Call `list_cameras` with the bridge id.
2. Done when `status` is `succeeded`. Pick `tracks` from the `id` field of the cameras the user named. An empty `tracks` list means every camera.
3. Call `download_history` with `start` and `end` as ISO-8601 timestamps that include a numeric offset (`2026-10-30T10:28:00-04:00`). The gateway converts them to the bridge's local time.
4. Done when `status` is `succeeded`. Each entry in `recordings` that has `uploaded: true` has a `url`. Give the user those URLs, the names, and the window you asked for. On any other status, tell the user `error_code` and stop.

A refused credential comes back as `auth_rejected`. Report it once. Do not call the tool again with the same credential.
