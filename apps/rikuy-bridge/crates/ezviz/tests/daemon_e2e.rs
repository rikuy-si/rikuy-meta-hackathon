//! End to end: backend job -> ezviz daemon -> ONVIF camera -> artifact ->
//! object storage -> report, with the same guarantees as the Hikvision bridge.
use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};

use rikuy_bridge_mocks::backend::{object_key, MockBackend};
use rikuy_bridge_mocks::objstore::MockObjectStore;
use rikuy_bridge_mocks::onvif::{MockOnvif, OnvifConfig};
use serde_json::json;

const BIN: &str = env!("CARGO_BIN_EXE_rikuy-bridge-ezviz");
const GOOD: &str = "ABCDEF";
const BAD: &str = "wrong-password-7731";
const TOKEN: &str = "bridge-token-ezviz";
const BRIDGE: &str = "site-ezviz-01";

fn job(id: &str, base: &str, pass: &str, kind: serde_json::Value) -> serde_json::Value {
    let mut j = json!({
        "id": id,
        "device": { "family": "ezviz", "base_url": base },
        "credential": { "username": "admin", "password": pass },
    });
    j.as_object_mut().unwrap().extend(kind.as_object().unwrap().clone());
    j
}

fn tempdir(tag: &str) -> PathBuf {
    let n = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
    std::env::temp_dir().join(format!("rikuy-ezviz-e2e-{tag}-{}-{n}", std::process::id()))
}

fn daemon(backend: &MockBackend, spool: &Path) -> Output {
    let token = spool.with_extension("token");
    std::fs::write(&token, TOKEN).unwrap();
    Command::new(BIN)
        .args([
            "daemon", "--backend", &backend.base_url, "--token-file", token.to_str().unwrap(),
            "--spool", spool.to_str().unwrap(), "--bridge-id", BRIDGE,
            "--poll-interval-ms", "50", "--unreachable-backoff-ms", "50", "--exit-when-idle",
        ])
        .output()
        .unwrap()
}

fn all_bytes_under(dir: &Path) -> Vec<u8> {
    let mut out = Vec::new();
    if let Ok(rd) = std::fs::read_dir(dir) {
        for e in rd {
            let p = e.unwrap().path();
            if p.is_dir() {
                out.extend(all_bytes_under(&p));
            } else {
                out.extend(std::fs::read(&p).unwrap());
            }
        }
    }
    out
}

fn contains(hay: &[u8], needle: &str) -> bool {
    hay.windows(needle.len()).any(|w| w == needle.as_bytes())
}

#[test]
fn backend_orchestrates_ezviz_over_onvif() {
    let cam = MockOnvif::start(OnvifConfig::ezviz_two_channel());
    let store = MockObjectStore::start();
    let backend = MockBackend::start_with_store(TOKEN, store.handle());
    let dead = format!("http://127.0.0.1:{}", TcpListener::bind("127.0.0.1:0").unwrap().local_addr().unwrap().port());
    let d = &cam.base_url;

    backend.enqueue(job("e1-cameras", d, GOOD, json!({ "kind": "list_cameras" })));
    backend.enqueue(job("e2-snapshot", d, GOOD, json!({ "kind": "snapshot", "channel": 1 })));
    backend.enqueue(job("e3-download", d, GOOD, json!({ "kind": "download", "from": "2026-10-30T10:28:00", "to": "2026-10-30T10:37:00", "tracks": [1] })));
    backend.enqueue(job("e4-search", d, GOOD, json!({ "kind": "search", "from": "2026-10-30T10:00:00", "to": "2026-10-30T11:00:00" })));
    backend.enqueue(job("e5-badcred", d, BAD, json!({ "kind": "list_cameras" })));
    backend.enqueue(job("e6-badcred-again", d, BAD, json!({ "kind": "snapshot", "channel": 1 })));
    backend.enqueue(job("e7-dead-route", &dead, GOOD, json!({ "kind": "snapshot", "channel": 1 })));
    backend.enqueue(job("e8-no-channel", d, GOOD, json!({ "kind": "snapshot", "channel": 9 })));
    let mut hik = job("e9-other-family", d, GOOD, json!({ "kind": "list_cameras" }));
    hik["device"]["family"] = json!("hikvision");
    backend.enqueue(hik);

    let spool = tempdir("spool");
    let out = daemon(&backend, &spool);
    let logs = format!("{}{}", String::from_utf8_lossy(&out.stdout), String::from_utf8_lossy(&out.stderr));
    assert!(out.status.success(), "{logs}");
    assert_eq!(backend.reports().len(), 9, "{logs}");

    let r1 = backend.report_for("e1-cameras").unwrap();
    assert_eq!(r1["status"], "succeeded");
    assert_eq!(r1["family"], "ezviz");
    assert_eq!(r1["data"].as_array().unwrap().len(), 2);

    let r2 = backend.report_for("e2-snapshot").unwrap();
    assert_eq!(r2["status"], "succeeded", "{r2:#}");
    assert_eq!(r2["artifacts"][0]["uploaded"], true);
    let jpeg = backend.artifact("e2-snapshot", "snapshot-cam1.jpg").unwrap();
    assert_eq!(&jpeg[..2], &[0xFF, 0xD8]);

    // Recordings: MP4 in object storage, byte-exact, spool cleaned after verification.
    let r3 = backend.report_for("e3-download").unwrap();
    assert_eq!(r3["status"], "succeeded", "{r3:#}\n{logs}");
    let arts = r3["artifacts"].as_array().unwrap();
    assert_eq!(arts.len(), 2);
    for a in arts {
        let name = a["name"].as_str().unwrap();
        assert!(name.ends_with(".mp4"));
        let key = object_key(BRIDGE, "e3-download", name);
        assert_eq!(a["object_key"], key);
        let (size, sha) = store.head(&key).expect("object stored");
        assert_eq!(size, a["bytes"].as_u64().unwrap());
        assert_eq!(sha, a["sha256"].as_str().unwrap());
        assert!(!spool.join("e3-download").join(name).exists(), "verified recording left in the spool");
    }

    let r4 = backend.report_for("e4-search").unwrap();
    // Both cameras: channel 1 has a gap (2 segments), channel 2 is continuous.
    assert_eq!(r4["data"].as_array().unwrap().len(), 3, "{r4:#}");

    assert_eq!(backend.report_for("e5-badcred").unwrap()["status"], "auth_rejected");
    assert_eq!(backend.report_for("e6-badcred-again").unwrap()["status"], "auth_rejected");
    let s = cam.stats();
    assert_eq!(s.bad_auth, 1, "the bad credential reached the camera more than once");
    assert!(!s.locked);

    assert_eq!(backend.report_for("e7-dead-route").unwrap()["error_code"], "unreachable");
    assert_eq!(backend.report_for("e8-no-channel").unwrap()["error_code"], "usage");
    assert_eq!(backend.report_for("e9-other-family").unwrap()["error_code"], "unsupported");

    let reports = serde_json::to_vec(&backend.reports()).unwrap();
    for secret in [GOOD, BAD] {
        assert!(!contains(&reports, secret), "secret in reports");
        assert!(!contains(&all_bytes_under(&spool), secret), "secret in spool");
        assert!(!logs.contains(secret), "secret in logs");
    }
}
