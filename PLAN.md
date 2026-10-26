# Rikuy Connect — Hackathon Plan (High Level)

Meta Global AI Developer Hackathon (Cerebral Valley x Meta). Window: **Oct 26 – Nov 4, 2026, 5:00 pm (UTC-5) submission deadline.**

## Goal

One safe connection layer that lets AI agents see through any camera: local Rust connectors on the customer's network, a FastMCP gateway as the single contract, and agent skills that make real video tasks (live image, historical clip retrieval, cloud upload) trivially easy for end users.

## Architecture (1000 ft)

```
[AI agent + skills]
        |
        | MCP / REST
        v
[FastMCP gateway (Python)]  -- grants, audit, revocation
        |
        | connector protocol (HTTPS/WS to customer network)
        v
[Rust binaries on customer network]  -- one per device family
   - hiklook  -> Hikvision / HiLook DVR/NVR (ISAPI + RTSP)
   - ezviz    -> Ezviz cloud cameras
        |
        v
[Cloudflare R2]  -- archived clips & evidence
```

## Repository structure

Modeled after the main `rikuy` monorepo (`apps/`, `packages/`, `infra/`):

```
apps/gateway/        FastMCP backend (Python + Pydantic AI integration)
binaries/hiklook/    Rust connector: Hikvision/HiLook DVR/NVR via ISAPI/RTSP
binaries/ezviz/      Rust connector: Ezviz cameras
skills/rikuy-video/  Core agent skill: video download/live image via MCP
skills/<use-case>/   End-user use-case skills (one dir per scenario)
demo/                POC artifacts, demo video, submission material
infra/               R2 buckets, deployment, env/secrets
```

## Workstreams

Effort: S (< half day), M (~1 day), L (2+ days) — sequential per stream, parallel across streams.

| # | Workstream | Effort | Start | End | Notes |
|---|------------|--------|-------|-----|-------|
| 1 | Repo scaffolding + architecture (this plan, AGENTS.md, README) | S | Oct 26 | Oct 26 | Done — Day 0 commits |
| 2 | `binaries/hiklook` — Rust connector for Hikvision/HiLook: auth, ISAPI channel discovery, live snapshot (RTSP→JPEG), playback download (RTSP over ISAPI), upload handshake to gateway | L | Oct 26 | Oct 29 | Hardest connector; validate on real DVR |
| 3 | `binaries/ezviz` — Rust connector for Ezviz cameras: login/session, live snapshot, recording download | M | Oct 27 | Oct 30 | Reuse hiklook connector crate (protocol + upload client) |
| 4 | `apps/gateway` — FastMCP backend: MCP tools (`list_cameras`, `live_image`, `download_history`, `upload_to_r2`), grants/audit log/revocation, connector registration, Pydantic AI agent integration | L | Oct 27 | Oct 31 | Tools defined contract-first so skills can start against stubs |
| 5 | `skills/rikuy-video` — agent skill: how to ask the MCP for a live image, download a historical range, push to R2, and return a shareable URL | M | Oct 31 | Nov 1 | Depends on 4 (tools stable) |
| 6 | End-user use-case skills — one skill per scenario (e.g. "did the salon open on time", "find the moment X happened and save the clip", "package left at the door") | M | Nov 1 | Nov 2 | Depends on 5 |
| 7 | POC + demo video — recorded agent runs end-to-end on this architecture (agent → skill → MCP → rust connector → camera → R2), edited submission video | M | Nov 2 | Nov 3 | Depends on 2–6 |
| 8 | Polish + submission — README, screenshots, submission form, final push | S | Nov 3 | Nov 4 (5 pm UTC-5) | Hard deadline; no new features after Nov 3 |

## Critical path

`hiklook (2)` → `gateway tools (4)` → `rikuy-video skill (5)` → `use-case skills (6)` → `POC + video (7)` → `submission (8)`.

Ezviz (3) runs parallel off the shared connector crate; it enriches the demo but is not on the critical path.

## Milestones

- **Oct 29** — Real Hikvision/HiLook DVR answering live snapshots + playback downloads via `hiklook`.
- **Oct 31** — Gateway MCP server live: agent can call `live_image` and `download_history` against a real camera, audit log written.
- **Nov 1** — Agent completes a full task unassisted via `rikuy-video` skill (live image + historical clip uploaded to R2 with returned URL).
- **Nov 2** — Use-case skills demonstrated on 2–3 scenarios.
- **Nov 3** — POC recorded end-to-end; demo video cut.
- **Nov 4, 5:00 pm (UTC-5)** — Submitted.

## Risks & mitigations

- **Real device access** (DVR behind customer network, firmware quirks): start connector work Day 1; keep a simulated/mock connector to unblock gateway and skills if hardware is delayed.
- **Skill quality (agent reliability)**: skills developed against stable tool schemas from Oct 31; keep scenarios narrow and rehearsed.
- **Demo risk**: record everything as soon as each milestone lands; never let the video depend on unfinished work.

## Definition of done (hackathon)

Working end-to-end: an AI agent, given a natural-language task, uses Rikuy skills → FastMCP gateway → Rust connector on the customer network → camera, retrieves live or historical video, uploads evidence to Cloudflare R2, and returns the result — with permissions and audit trail. Captured on video and submitted before Nov 4, 5:00 pm (UTC-5).
