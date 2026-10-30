//! The Ezviz scaffold speaks the full backend contract through `common`.
use std::process::Command;

use rikuy_bridge_mocks::backend::MockBackend;
use serde_json::json;

#[test]
fn ezviz_daemon_reuses_common_contract() {
    let backend = MockBackend::start("tok");
    let job = |id: &str, family: &str| {
        json!({
            "id": id,
            "device": { "family": family, "base_url": "http://192.0.2.10" },
            "credential": { "username": "admin", "password": "ezviz-secret-55" },
            "kind": "snapshot", "channel": 1
        })
    };
    backend.enqueue(job("e1", "ezviz"));
    backend.enqueue(job("e2", "hikvision"));
    let dir = std::env::temp_dir().join(format!("rikuy-ezviz-{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(dir.join("token"), "tok").unwrap();
    let out = Command::new(env!("CARGO_BIN_EXE_rikuy-bridge-ezviz"))
        .args(["daemon", "--backend", &backend.base_url, "--token-file", dir.join("token").to_str().unwrap(),
               "--spool", dir.join("spool").to_str().unwrap(), "--poll-interval-ms", "50", "--exit-when-idle"])
        .output()
        .unwrap();
    let logs = String::from_utf8_lossy(&out.stderr).to_string();
    assert!(out.status.success(), "{logs}");

    let e1 = backend.report_for("e1").unwrap();
    assert_eq!(e1["family"], "ezviz");
    assert_eq!(e1["status"], "failed");
    assert_eq!(e1["error_code"], "unsupported");
    assert!(e1["error_message"].as_str().unwrap().contains("snapshot"));
    let e2 = backend.report_for("e2").unwrap();
    assert!(e2["error_message"].as_str().unwrap().contains("serves ezviz"));
    assert!(!logs.contains("ezviz-secret-55"));
}
