# Implementation plan: rikuy-bridge Hikvision connector

Status: planned. Date: 2026-10-26.
Covers PLAN.md workstreams 2 (Hikvision connector) and 3 (Ezviz scaffold).

## 1. Question

Can a Rust workspace built around the field-validated Hikvision ISAPI flow do
the full job a bridge needs to do? The job is: receive a job and its
credential from the backend, run the ISAPI calls, produce the artifact, and
report back. If so, the workspace becomes `apps/rikuy-bridge/`.

## 2. Hypotheses

- **H1.** A plain Rust client (Digest auth + XML) is enough to cover
  `tracks → paged search → POST download → snapshot`. No vendor SDK is needed.
- **H2.** A shared `common` crate can hold the job, report, credential and
  retry contract, so the Ezviz bridge reuses it unchanged.
- **H3.** A daemon can hold the device credential in memory only, per job, and
  still recover from a dead route or rejected auth without hammering the
  device. Rejected auth means exiting with code 77, with no retry.
- **H4.** The workspace cross-compiles to `x86_64-pc-windows-gnu`, which is
  the customer host's OS.
- **H5 (optional).** A time-boxed reverse-engineering pass over the iVMS-4200
  desktop client confirms or extends the ISAPI reference, for example playback
  URI formats or channel numbering.

## 3. Target layout

```
apps/rikuy-bridge/
├── crates/                   # Cargo workspace
│   ├── Cargo.toml
│   ├── common/               # job, report, credential envelope, retry/liveness
│   ├── hikvision/            # bin: rikuy-bridge-hikvision
│   ├── ezviz/                # bin: rikuy-bridge-ezviz (scaffold + TODO stubs)
│   └── docs/
│       ├── backend-contract.md
│       ├── windows.md
│       └── reverse-notes.md  # only if H5 is attempted
└── mocks/                    # mock ISAPI DVR, mock backend, XML fixtures
```

## 4. ISAPI reference

| Concern | Fact |
|---|---|
| Auth | HTTP Digest. 401/403 can lock the account, so abort immediately with exit code 77. |
| Discovery | `GET /ISAPI/ContentMgmt/record/tracks` returns XML. |
| Search | `POST /ISAPI/ContentMgmt/search` with a `CMSearchDescription` body. Pages are capped at 64 results; paginate until the range is covered. |
| Download | `POST /ISAPI/ContentMgmt/download` with body `<downloadRequest><playbackURI>rtsp://…</playbackURI></downloadRequest>`. The GET form returns 400. The RTSP URI is only an identifier. |
| Snapshot | `GET /ISAPI/Streaming/channels/<n>/picture` returns a JPEG. |
| Liveness | Check the route before every request, and never blind-retry against a dead listener. |
| Time | Timestamps carry a `Z` suffix but are local wall-clock time (UTC−5). |
| Output | A `.dav` file is the raw stream plus a 40-byte `IMKH` wrapper: H.264 1280×720 video with µ-law audio. |

## 5. Steps

Each step ends with a commit.

1. **Scaffold.** Create the Cargo workspace, the `common` types (job, report,
   credential envelope) and the `hikvision`/`ezviz` crate skeletons, and
   outline the docs.
2. **Mocks.** Build a mock ISAPI server with Digest auth, tracks, paged
   search, POST-only download, snapshot and a lockout simulation. Build a mock
   backend with a job queue and a report sink. Add realistic XML fixtures.
3. **ISAPI client.** Implement Digest auth, tracks and paged search, and get
   them passing against the mock (H1).
4. **Media.** Add `screenshot` and `download`, liveness checks, exit 77 on
   401/403, and `IMKH` header validation on downloads (H1, H3).
5. **Daemon.** The daemon polls jobs, receives the credential per job,
   executes, reports, and never writes the secret to disk. Add an end-to-end
   integration test: job → ISAPI → artifact → report (H3).
6. **Ezviz scaffold.** Wire the job loop to `common`, and leave the protocol
   client as documented stubs (H2).
7. **Windows.** Run `cargo build --target x86_64-pc-windows-gnu` and write the
   deployment notes (H4).
8. **Reverse pass (optional, ≤ 90 min).** Static `strings` pass over the
   iVMS-4200 client, read-only, without opening media. Document the pass even
   if it is inconclusive (H5).
9. **Results.** Consolidate the backend contract and the workspace README;
   record which hypotheses are confirmed or refuted, separating evidence from
   assumptions.

## 6. Bridge CLI (target)

```
rikuy-bridge-hikvision list-cameras --device <url>
rikuy-bridge-hikvision screenshot   --device <url> --channel <n> --out <file.jpg>
rikuy-bridge-hikvision search       --device <url> --from <ts> --to <ts> [--track <id>]
rikuy-bridge-hikvision download     --device <url> --from <ts> --to <ts> --out <dir>
rikuy-bridge-hikvision daemon       --backend <url> --token-file <path>
```

Device credentials for the one-shot commands come from an environment variable
or stdin, never from argv or a file in the repo. Daemon mode gets them per job
from the backend.

## 7. Success criteria

- `cargo build` and `cargo test` pass for the whole workspace.
- The integration test covers the full job → report path for both a snapshot
  job and a download job.
- A rejected-auth scenario stops after one attempt with exit 77. A dead-route
  scenario fails fast without a retry storm.
- The Windows GNU build succeeds, or the blocker is documented.
- No secrets, customer IPs, account names or media appear in the repository.

## 8. Out of scope

- Real Ezviz protocol work, gateway (`apps/gateway`) work, R2 upload, and
  agent skills.
- Any access to the customer DVR or relay without explicit approval at that
  moment.
