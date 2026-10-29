//! End to end: backend job -> bridge daemon -> ISAPI device -> artifact -> report.
use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};

use rikuy_bridge_mocks::backend::MockBackend;
use rikuy_bridge_mocks::isapi::{IsapiConfig, MockIsapi};
use serde_json::json;

const BIN: &str = env!("CARGO_BIN_EXE_rikuy-bridge-hikvision");
const GOOD: &str = "correct-horse";
const BAD: &str = "wrong-password-7731";
const TOKEN: &str = "bridge-token-e2e";

fn job(id: &str, base: &str, pass: &str, kind: serde_json::Value) -> serde_json::Value {
    let mut j = json!({
        "id": id,
        "device": { "family": "hikvision", "base_url": base },
        "credential": { "username": "admin", "password": pass },
    });
    j.as_object_mut().unwrap().extend(kind.as_object().unwrap().clone());
    j
}

fn daemon(backend: &MockBackend, spool: &Path, token: &str) -> Output {
    let token_file = spool.with_extension("token");
    std::fs::write(&token_file, format!("{token}\n")).unwrap();
    Command::new(BIN)
        .args([
            "daemon",
            "--backend", &backend.base_url,
            "--token-file", token_file.to_str().unwrap(),
            "--spool", spool.to_str().unwrap(),
            "--bridge-id", "e2e-bridge",
            "--poll-interval-ms", "50",
            "--unreachable-backoff-ms", "50",
            "--exit-when-idle",
        ])
        .output()
        .unwrap()
}

fn tempdir(tag: &str) -> PathBuf {
    let n = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
    std::env::temp_dir().join(format!("rikuy-bridge-e2e-{tag}-{}-{n}", std::process::id()))
}

fn all_bytes_under(dir: &Path) -> Vec<u8> {
    let mut out = Vec::new();
    for e in std::fs::read_dir(dir).unwrap() {
        let p = e.unwrap().path();
        if p.is_dir() {
            out.extend(all_bytes_under(&p));
        } else {
            out.extend(std::fs::read(&p).unwrap());
        }
    }
    out
}

fn contains(hay: &[u8], needle: &str) -> bool {
    hay.windows(needle.len()).any(|w| w == needle.as_bytes())
}

#[test]
fn backend_orchestrates_snapshot_download_and_failures() {
    let dvr = MockIsapi::start(IsapiConfig::eight_channel_dvr(8));
    let backend = MockBackend::start(TOKEN);
    let dead = format!("http://127.0.0.1:{}", TcpListener::bind("127.0.0.1:0").unwrap().local_addr().unwrap().port());
    let d = &dvr.base_url;

    backend.enqueue(job("j1-snapshot", d, GOOD, json!({ "kind": "snapshot", "channel": 2 })));
    backend.enqueue(job("j2-download", d, GOOD, json!({ "kind": "download", "from": "2026-10-29T05:00:00", "to": "2026-10-29T06:00:00", "tracks": [101] })));
    backend.enqueue(job("j3-cameras", d, GOOD, json!({ "kind": "list_cameras" })));
    backend.enqueue(job("j4-badcred", d, BAD, json!({ "kind": "list_cameras" })));
    backend.enqueue(job("j5-badcred-again", d, BAD, json!({ "kind": "snapshot", "channel": 1 })));
    backend.enqueue(job("j6-dead-route", &dead, GOOD, json!({ "kind": "snapshot", "channel": 1 })));
    let mut ezviz = job("j7-other-family", d, GOOD, json!({ "kind": "snapshot", "channel": 1 }));
    ezviz["device"]["family"] = json!("ezviz");
    backend.enqueue(ezviz);
    backend.enqueue(json!({ "id": "j8-malformed", "kind": "snapshot" }));
    backend.enqueue(json!({ "id": "../../escape", "kind": "list_cameras" }));

    let spool = tempdir("spool");
    let out = daemon(&backend, &spool, TOKEN);
    let logs = format!("{}{}", String::from_utf8_lossy(&out.stdout), String::from_utf8_lossy(&out.stderr));
    assert!(out.status.success(), "{logs}");
    assert_eq!(backend.reports().len(), 9, "{logs}");

    // Snapshot: produced, uploaded to the backend, reported with its hash.
    let r1 = backend.report_for("j1-snapshot").unwrap();
    assert_eq!(r1["status"], "succeeded");
    assert_eq!(r1["artifacts"][0]["kind"], "snapshot");
    assert_eq!(r1["artifacts"][0]["uploaded"], true);
    let jpeg = backend.artifact("j1-snapshot", "snapshot-cam2.jpg").unwrap();
    assert_eq!(&jpeg[..2], &[0xFF, 0xD8]);

    // Download: 4 x 15 min recordings land in the job's spool directory.
    let r2 = backend.report_for("j2-download").unwrap();
    assert_eq!(r2["status"], "succeeded");
    assert_eq!(r2["artifacts"].as_array().unwrap().len(), 4);
    for a in r2["artifacts"].as_array().unwrap() {
        let b = std::fs::read(spool.join("j2-download").join(a["name"].as_str().unwrap())).unwrap();
        assert_eq!(&b[..4], b"IMKH");
        assert_eq!(a["bytes"].as_u64().unwrap(), b.len() as u64);
        assert_eq!(a["uploaded"], false);
    }

    let r3 = backend.report_for("j3-cameras").unwrap();
    assert_eq!(r3["data"].as_array().unwrap().len(), 8);

    // Rejected credential: one credentialed attempt, then never sent again.
    assert_eq!(backend.report_for("j4-badcred").unwrap()["status"], "auth_rejected");
    assert_eq!(backend.report_for("j5-badcred-again").unwrap()["status"], "auth_rejected");
    let s = dvr.stats();
    assert_eq!(s.bad_auth, 1, "the bad credential reached the device more than once");
    assert!(!s.locked);

    assert_eq!(backend.report_for("j6-dead-route").unwrap()["error_code"], "unreachable");
    assert_eq!(backend.report_for("j7-other-family").unwrap()["error_code"], "unsupported");
    assert_eq!(backend.report_for("j8-malformed").unwrap()["error_code"], "invalid_job");
    assert_eq!(backend.report_for("../../escape").unwrap()["error_code"], "invalid_job");
    assert!(!spool.parent().unwrap().join("escape").exists());

    // No credential anywhere: reports, spool, logs.
    let reports = serde_json::to_vec(&backend.reports()).unwrap();
    for secret in [GOOD, BAD] {
        assert!(!contains(&reports, secret), "secret in reports");
        assert!(!contains(&all_bytes_under(&spool), secret), "secret in spool");
        assert!(!logs.contains(secret), "secret in logs");
    }
}

#[test]
fn rejected_bridge_token_stops_the_daemon_with_77() {
    let backend = MockBackend::start(TOKEN);
    let spool = tempdir("token");
    let out = daemon(&backend, &spool, "not-the-token");
    assert_eq!(out.status.code(), Some(77), "{}", String::from_utf8_lossy(&out.stderr));
    assert_eq!(backend.unauthorized(), 1, "must not keep polling with a rejected token");
}
