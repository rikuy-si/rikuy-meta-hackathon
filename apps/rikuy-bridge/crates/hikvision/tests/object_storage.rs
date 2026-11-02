//! Recordings: DVR -> bridge spool -> presigned PUT -> object store -> backend
//! verifies -> bridge deletes from the spool.
use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};

use rikuy_bridge_mocks::backend::{object_key, MockBackend};
use rikuy_bridge_mocks::isapi::{IsapiConfig, MockIsapi};
use rikuy_bridge_mocks::objstore::MockObjectStore;
use serde_json::json;

const BIN: &str = env!("CARGO_BIN_EXE_rikuy-bridge-hikvision");
const TOKEN: &str = "bridge-token-r2";
const BRIDGE: &str = "site-test-01";

fn tempdir(tag: &str) -> PathBuf {
    let n = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
    let d = std::env::temp_dir().join(format!("rikuy-bridge-r2-{tag}-{}-{n}", std::process::id()));
    std::fs::create_dir_all(&d).unwrap();
    d
}

fn download_job(id: &str, dvr: &str) -> serde_json::Value {
    json!({
        "id": id,
        "device": { "family": "hikvision", "base_url": dvr },
        "credential": { "username": "admin", "password": "correct-horse" },
        "kind": "download", "from": "2026-10-29T05:00:00", "to": "2026-10-29T06:00:00", "tracks": [101, 201]
    })
}

fn daemon(backend: &MockBackend, spool: &Path, batch: &str) -> Output {
    let token = spool.with_extension("token");
    std::fs::write(&token, TOKEN).unwrap();
    Command::new(BIN)
        .args([
            "daemon", "--backend", &backend.base_url, "--token-file", token.to_str().unwrap(),
            "--spool", spool.to_str().unwrap(), "--bridge-id", BRIDGE,
            "--poll-interval-ms", "50", "--exit-when-idle", "--upload-batch", batch,
        ])
        .output()
        .unwrap()
}

fn dav_files(dir: &Path) -> Vec<PathBuf> {
    std::fs::read_dir(dir)
        .map(|r| r.map(|e| e.unwrap().path()).filter(|p| p.extension().map(|x| x == "dav").unwrap_or(false)).collect())
        .unwrap_or_default()
}

#[test]
fn recordings_are_uploaded_verified_and_cleaned_from_spool() {
    let dvr = MockIsapi::start(IsapiConfig::eight_channel_dvr(8));
    let store = MockObjectStore::start();
    let backend = MockBackend::start_with_store(TOKEN, store.handle());
    // The first grant is already expired: the bridge must refresh it.
    backend.expire_next_grants(1);
    backend.enqueue(download_job("r1", &dvr.base_url));

    let spool = tempdir("ok");
    let out = daemon(&backend, &spool, "3");
    let logs = String::from_utf8_lossy(&out.stderr).to_string();
    assert!(out.status.success(), "{logs}");

    let r = backend.report_for("r1").unwrap();
    assert_eq!(r["status"], "succeeded", "{r:#}\n{logs}");
    let arts = r["artifacts"].as_array().unwrap();
    assert_eq!(arts.len(), 8);

    // Every recording is in the store under the backend-chosen key, byte-exact.
    for a in arts {
        let name = a["name"].as_str().unwrap();
        let key = object_key(BRIDGE, "r1", name);
        assert_eq!(a["uploaded"], true);
        assert_eq!(a["object_key"], key);
        let (size, sha) = store.head(&key).expect("object stored");
        assert_eq!(size, a["bytes"].as_u64().unwrap());
        assert_eq!(sha, a["sha256"].as_str().unwrap());
    }
    // The stored bytes are real DVR recordings (IMKH wrapper), matching the clips.
    let clips = dvr.clips();
    let first = arts[0]["name"].as_str().unwrap();
    assert!(clips.iter().any(|c| c.size + 40 == store.head(&object_key(BRIDGE, "r1", first)).unwrap().0));

    assert_eq!(store.puts(), 8, "one PUT per recording");
    assert_eq!(store.rejected_expired(), 1, "the expired grant was tried once");
    assert_eq!(store.rejected_other(), 0, "no chunked or mis-sized uploads");
    // 8 files in batches of 3 = 3 grant requests, + 1 refresh for the expired URL.
    assert_eq!(backend.upload_requests(), 4);
    assert_eq!(backend.verified(), 8);

    // Verified -> deleted locally; the manifest stays as the local record.
    assert!(dav_files(&spool.join("r1")).is_empty(), "spool still holds recordings");
    assert!(spool.join("r1/manifest.json").exists());

    // The backend token never went to the object store, and no secrets in logs.
    assert!(!logs.contains(TOKEN) && !logs.contains("correct-horse"));
}

#[test]
fn rerun_does_not_reupload_objects_already_stored() {
    let dvr = MockIsapi::start(IsapiConfig::eight_channel_dvr(8));
    let store = MockObjectStore::start();
    let backend = MockBackend::start_with_store(TOKEN, store.handle());
    backend.enqueue(download_job("r2", &dvr.base_url));
    backend.enqueue(download_job("r2", &dvr.base_url)); // the backend re-issues the same job
    let spool = tempdir("rerun");
    let out = daemon(&backend, &spool, "16");
    assert!(out.status.success(), "{}", String::from_utf8_lossy(&out.stderr));
    assert_eq!(backend.reports().len(), 2);
    let second = backend.report_for("r2").unwrap();
    assert_eq!(second["status"], "succeeded");
    assert!(second["artifacts"].as_array().unwrap().iter().all(|a| a["uploaded"] == true));
    assert_eq!(store.puts(), 8, "second run found every object already stored");
    assert_eq!(backend.grants_issued(), 8);
}

#[test]
fn unreachable_object_store_keeps_recordings_and_reports_partial() {
    let dvr = MockIsapi::start(IsapiConfig::eight_channel_dvr(8));
    let store = MockObjectStore::start();
    let backend = MockBackend::start_with_store(TOKEN, store.handle());
    let dead = format!("http://127.0.0.1:{}", TcpListener::bind("127.0.0.1:0").unwrap().local_addr().unwrap().port());
    backend.override_grant_base(&dead);
    backend.enqueue(download_job("r3", &dvr.base_url));
    let spool = tempdir("dead");
    let out = daemon(&backend, &spool, "16");
    assert!(out.status.success(), "{}", String::from_utf8_lossy(&out.stderr));

    let r = backend.report_for("r3").unwrap();
    assert_eq!(r["status"], "partial");
    assert_eq!(r["error_code"], "upload");
    assert!(r["artifacts"].as_array().unwrap().iter().all(|a| a["uploaded"] == false));
    assert_eq!(backend.verified(), 0);
    // Nothing was confirmed, so nothing was deleted: the next attempt can resume.
    let files = dav_files(&spool.join("r3"));
    assert_eq!(files.len(), 8);
    for f in files {
        let b = std::fs::read(&f).unwrap();
        assert_eq!(&b[..4], b"IMKH");
    }
}
