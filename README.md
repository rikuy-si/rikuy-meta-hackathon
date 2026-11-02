# Rikuy Connect

One safe connection layer that lets AI agents see through any camera in the world.

## Built during the hackathon

This repository was created on October 26, 2026 for the Meta Global AI Developer Hackathon (Cerebral Valley x Meta, Oct 26 - Nov 4, 2026). All code in this repository was written during the event. Pre-existing work: none in this repository.

## What we are building

Rikuy Connect is a local gateway that turns any camera (RTSP/ONVIF cameras, Hikvision/HiLook DVR/NVRs, phone and webcams over WebRTC) into one interface that AI agents can use, with permissions, audit and revocation.

## Planned architecture

- Local gateway with connectors: RTSP/ONVIF, Hikvision/HiLook ISAPI, WebRTC for phones and webcams.
- REST and MCP contract for agents, with grants, audit log and revocation.
- Meta AI: Muse Spark as the agent, SAM 3.1 for face anonymization and text search across cameras, Muse Spark Open on Baseten for cheap triage.

## Status

Day 8 (Nov 2). `apps/rikuy-bridge` is in place: the Hikvision/HiLook
connector (ISAPI + RTSP) runs as a CLI and as a backend-driven daemon, with
27 green tests against the mock DVR, backend and R2 stand-in. The Ezviz
connector speaks ONVIF (Profile T live snapshot, Profile G replay to MP4)
on that same contract, validated against a mock camera. Recordings are delivered
to object storage via backend-issued presigned PUT URLs, and the workspace
cross-compiles to Windows (`x86_64-pc-windows-gnu`).

The FastMCP gateway (`apps/gateway`) is live on the same contract: MCP tools
(`list_cameras`, `live_image`, `download_history`, `upload_to_r2`) with
per-actor grants, audit log and revocation, plus presigned R2 uploads —
proven end-to-end against the Hikvision daemon and the mock DVR, and
against the Ezviz daemon and the mock ONVIF camera.

Next on the critical path: the `rikuy-video` agent skill, use-case skills,
and the demo video. See PLAN.md for the workstream schedule and TODO.md for
what is left.
