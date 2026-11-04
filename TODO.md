# Rikuy Connect — TODO

**Deadline: Nov 4, 2026, 9:00 pm ET (UTC-5).**

## Done

- [x] WS1 — Repo scaffolding: PLAN.md, AGENTS.md, README, license (Oct 26).
- [x] WS2 — Hikvision connector (`apps/rikuy-bridge`): ISAPI client with digest
      auth, liveness probe, track discovery, paged search; `screenshot` and
      `download` commands with IMKH/size validation and idempotent resume;
      daemon mode with backend job polling, per-job in-memory credentials,
      rejected-credential memory, artifact upload. 27 tests green, clippy
      clean, validated end-to-end against the mock DVR, backend and R2
      stand-in. Connector docs under `apps/rikuy-bridge/crates/docs/`.
- [x] WS3 — Ezviz connector (`apps/rikuy-bridge`): ONVIF Profile T live
      snapshot and Profile G search/replay to MP4, on the shared daemon.
      Validated against the mock camera and through the gateway. The bridge
      host needs ffmpeg and ffprobe.
- [x] Recording delivery to object storage via backend-issued presigned PUT
      URLs, spool cleanup after backend HEAD verification (byte-exact against
      the R2 stand-in; idempotent re-runs; nothing lost on partial failure).
- [x] Windows cross-build (`x86_64-pc-windows-gnu` via zig): PE32+ console
      binaries build; runtime unverified.
- [x] Static reverse pass over iVMS-4200 (`apps/rikuy-bridge/crates/docs/reverse-notes.md`): endpoint
      shapes confirmed, 5 new protocol leads.

## Critical path — do in this order

- [x] 1. **Promote the bridge workspace** into this repo as `apps/rikuy-bridge/`
       — done Nov 2 (`crates/` + `mocks/`); see
       `docs/planning/2026-10-26/hikvision-bridge.md`. — S
- [x] 2. **Gateway (WS4)** — done Oct 31: `apps/gateway` (FastMCP) speaks the
       backend contract, serves the four MCP tools with grants, audit log and
       revocation, and passes an e2e test with the real bridge daemon and the
       mock DVR. The Pydantic AI agent integration lands with the skill (WS5).
- [x] 3. **Real R2 presigned PUTs** — signing implemented (boto3 SigV4 against
       the R2 S3 endpoint); validate once against a real bucket before the
       demo.
- [x] 4. **`skills/rikuy-video` (WS5)** — done Nov 3: live image, historical
       range, upload, shareable URL. `skills/rikuy-video/SKILL.md`.
- [x] 5. **Use-case skills (WS6)** — done Nov 3: `shop-opened`, `find-moment`,
       `package-at-door`. Each one calls the rikuy-video procedure.
- [x] 6. **POC + demo video (WS7)** — done Nov 3: `demo/run_poc.py` runs the
       package-at-the-door skill against the mock Ezviz camera. Cut is
       `demo/poc.mp4`; still is `demo/artifacts/door.jpg`.
- [ ] 7. **Polish + submission (WS8)**: README rewritten for submission (Nov 4):
       pre-existing work, models table, Quickstart, limitations; `.env.example`
       added. Still open: demo video link in the README. Fill the hackathon form by hand before
       Nov 4, 9:00 pm ET (UTC-5). No new features after this. — S

## Blocked / conditional

- [ ] Live smoke test on the customer's Windows host (`list-cameras`,
      `screenshot`, a 15-minute `download`) — blocked on site access. Closes
      Windows-runtime validation and real-firmware ISAPI checks. Do it before
      the demo if the host comes back online; otherwise the mock-backed demo
      stands.
- [ ] Run the Windows `.exe` on Windows 10+ (local Wine 5.0.3 cannot load Rust
      std's `bcryptprimitives.dll` import).

## Optional — not on the critical path

- [ ] Zeroize intermediate credential copies in HTTP/Digest header strings.
- [ ] Native Windows service, code signing, bridge token rotation.

## Hygiene

- [x] Final README polish before submission (Nov 4); demo video link still to add.
- [x] Keep local scratch out of the submitted repository — `runs/` is
      gitignored and was never committed.
