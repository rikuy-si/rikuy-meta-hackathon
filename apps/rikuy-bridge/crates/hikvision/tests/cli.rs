use std::net::TcpListener;
use std::process::{Command, Output};
use std::time::{Duration, Instant};

use rikuy_bridge_mocks::isapi::{IsapiConfig, MockIsapi};

const BIN: &str = env!("CARGO_BIN_EXE_rikuy-bridge-hikvision");

fn run(args: &[&str], password: Option<&str>) -> Output {
    let mut c = Command::new(BIN);
    c.args(args).env_remove("RIKUY_DEVICE_PASSWORD").env_remove("RIKUY_DEVICE_USER");
    if let Some(p) = password {
        c.env("RIKUY_DEVICE_PASSWORD", p);
    }
    c.output().unwrap()
}

fn text(o: &Output) -> String {
    format!("{}{}", String::from_utf8_lossy(&o.stdout), String::from_utf8_lossy(&o.stderr))
}

#[test]
fn screenshot_writes_a_jpeg() {
    let dvr = MockIsapi::start(IsapiConfig::eight_channel_dvr(1));
    let dir = tempdir("shot");
    let out = dir.join("cam3.jpg");
    let o = run(&["screenshot", "--device", &dvr.base_url, "--channel", "3", "--out", out.to_str().unwrap()], Some("correct-horse"));
    assert!(o.status.success(), "{}", text(&o));
    let jpg = std::fs::read(&out).unwrap();
    assert_eq!(&jpg[..2], &[0xFF, 0xD8]);
    assert!(dvr.stats().requests.iter().any(|(_, p)| p == "/ISAPI/Streaming/channels/301/picture"));
}

#[test]
fn download_writes_wrapped_recordings_and_is_idempotent() {
    let dvr = MockIsapi::start(IsapiConfig::eight_channel_dvr(8));
    let dir = tempdir("dl");
    let args = ["download", "--device", &dvr.base_url, "--from", "2026-10-29T05:00:00", "--to", "2026-10-29T07:00:00", "--track", "101", "--track", "401", "--out", dir.to_str().unwrap()];
    let o = run(&args, Some("correct-horse"));
    assert!(o.status.success(), "{}", text(&o));
    let summary: serde_json::Value = serde_json::from_slice(&o.stdout).unwrap();
    assert_eq!(summary["found"], 16);
    assert_eq!(summary["downloaded"], 16);

    let clips = dvr.clips();
    let mut n = 0;
    for e in std::fs::read_dir(&dir).unwrap() {
        let p = e.unwrap().path();
        if p.extension().map(|x| x == "dav").unwrap_or(false) {
            let b = std::fs::read(&p).unwrap();
            assert_eq!(&b[..4], b"IMKH");
            assert!(clips.iter().any(|c| c.size + 40 == b.len() as u64));
            n += 1;
        }
    }
    assert_eq!(n, 16);
    let manifest: serde_json::Value = serde_json::from_slice(&std::fs::read(dir.join("manifest.json")).unwrap()).unwrap();
    assert_eq!(manifest["entries"].as_object().unwrap().len(), 16);
    assert_eq!(dvr.stats().get_download_hits, 0, "download must use POST");

    // Second run: everything is already on disk, nothing is downloaded again.
    let posts_before = count_downloads(&dvr);
    let o = run(&args, Some("correct-horse"));
    assert!(o.status.success(), "{}", text(&o));
    let summary: serde_json::Value = serde_json::from_slice(&o.stdout).unwrap();
    assert_eq!(summary["skipped_existing"], 16);
    assert_eq!(count_downloads(&dvr), posts_before);
}

#[test]
fn rejected_credential_exits_77_after_one_attempt_without_leaking_it() {
    let dvr = MockIsapi::start(IsapiConfig::eight_channel_dvr(4));
    let dir = tempdir("auth");
    let o = run(
        &["download", "--device", &dvr.base_url, "--from", "2026-10-29T05:00:00", "--to", "2026-10-29T06:00:00", "--out", dir.to_str().unwrap()],
        Some("hunter2-wrong"),
    );
    assert_eq!(o.status.code(), Some(77), "{}", text(&o));
    assert!(text(&o).contains("auth_rejected"));
    assert!(!text(&o).contains("hunter2-wrong"));
    let s = dvr.stats();
    assert_eq!(s.bad_auth, 1);
    assert!(!s.locked);
}

#[test]
fn dead_route_exits_69_fast_without_retrying() {
    // Reserve a port, then close it: nothing listens there.
    let port = TcpListener::bind("127.0.0.1:0").unwrap().local_addr().unwrap().port();
    let t = Instant::now();
    let o = run(&["list-cameras", "--device", &format!("http://127.0.0.1:{port}")], Some("x"));
    assert_eq!(o.status.code(), Some(69), "{}", text(&o));
    assert!(t.elapsed() < Duration::from_secs(5));
}

#[test]
fn corrupt_recording_exits_76_and_leaves_no_partial_file() {
    let mut cfg = IsapiConfig::eight_channel_dvr(2);
    cfg.corrupt_downloads = true;
    let dvr = MockIsapi::start(cfg);
    let dir = tempdir("corrupt");
    let o = run(
        &["download", "--device", &dvr.base_url, "--from", "2026-10-29T05:00:00", "--to", "2026-10-29T06:00:00", "--track", "101", "--out", dir.to_str().unwrap()],
        Some("correct-horse"),
    );
    assert_eq!(o.status.code(), Some(76), "{}", text(&o));
    let leftovers: Vec<_> = std::fs::read_dir(&dir).unwrap().map(|e| e.unwrap().file_name()).filter(|n| n != "manifest.json").collect();
    assert!(leftovers.is_empty(), "{leftovers:?}");
    assert_eq!(count_downloads(&dvr), 1, "stops at the first bad recording");
}

#[test]
fn missing_password_is_a_usage_error() {
    let o = run(&["list-cameras", "--device", "http://127.0.0.1:9"], None);
    assert_eq!(o.status.code(), Some(64), "{}", text(&o));
}

fn count_downloads(dvr: &MockIsapi) -> usize {
    dvr.stats().requests.iter().filter(|(m, p)| m == "POST" && p == "/ISAPI/ContentMgmt/download").count()
}

fn tempdir(tag: &str) -> std::path::PathBuf {
    let d = std::env::temp_dir().join(format!("rikuy-bridge-test-{tag}-{}-{}", std::process::id(), rand_suffix()));
    std::fs::create_dir_all(&d).unwrap();
    d
}

fn rand_suffix() -> u128 {
    std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos()
}
