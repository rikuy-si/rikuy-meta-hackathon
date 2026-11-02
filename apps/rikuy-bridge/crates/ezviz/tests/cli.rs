//! The real `rikuy-bridge-ezviz` binary against the mock ONVIF camera.
use std::path::{Path, PathBuf};
use std::process::{Command, Output};

use rikuy_bridge_mocks::onvif::{MockOnvif, OnvifConfig};
use serde_json::Value;

const BIN: &str = env!("CARGO_BIN_EXE_rikuy-bridge-ezviz");
const GOOD: &str = "ABCDEF";

fn tempdir(tag: &str) -> PathBuf {
    let n = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
    let d = std::env::temp_dir().join(format!("rikuy-ezviz-{tag}-{}-{n}", std::process::id()));
    std::fs::create_dir_all(&d).unwrap();
    d
}

fn run(device: &str, password: &str, args: &[&str]) -> Output {
    let mut cmd = Command::new(BIN);
    cmd.arg(args[0]).args(["--device", device]).args(&args[1..]);
    cmd.env("RIKUY_DEVICE_USER", "admin").env("RIKUY_DEVICE_PASSWORD", password);
    let out = cmd.output().unwrap();
    let all = format!("{}{}", String::from_utf8_lossy(&out.stdout), String::from_utf8_lossy(&out.stderr));
    assert!(!all.contains(password), "password leaked in CLI output");
    out
}

fn ok_json(out: Output) -> Value {
    assert!(out.status.success(), "{}", String::from_utf8_lossy(&out.stderr));
    serde_json::from_slice(&out.stdout).unwrap()
}

fn probe(p: &Path) -> Value {
    let o = Command::new("ffprobe")
        .args(["-v", "error", "-show_entries", "format=duration:stream=codec_type,codec_name", "-of", "json"])
        .arg(p)
        .output()
        .unwrap();
    assert!(o.status.success());
    serde_json::from_slice(&o.stdout).unwrap()
}

fn decodes_cleanly(p: &Path) -> bool {
    Command::new("ffmpeg").args(["-v", "error", "-xerror", "-i"]).arg(p).args(["-f", "null", "-"]).status().unwrap().success()
}

#[test]
fn cameras_snapshot_search_download_and_resume() {
    let cam = MockOnvif::start(OnvifConfig::ezviz_two_channel());
    let d = &cam.base_url;

    let info = ok_json(run(d, GOOD, &["device-info"]));
    assert_eq!(info["info"]["manufacturer"], "EZVIZ");
    assert!(info["profile_t_media2"].as_bool().unwrap() && info["profile_g_search"].as_bool().unwrap());
    // The camera clock is ~1 h fast; the bridge measures it instead of trusting its own.
    let skew = info["clock"]["skew_secs"].as_i64().unwrap();
    assert!((3600..=3605).contains(&skew), "skew {skew}");

    let cams = ok_json(run(d, GOOD, &["list-cameras"]));
    let cams = cams.as_array().unwrap();
    assert_eq!(cams.len(), 2);
    assert_eq!(cams[0]["encoding"], "H265");
    assert_eq!(cams[0]["profile_token"], "Profile_1_main", "main stream = highest resolution");
    assert_eq!(cams[0]["timezone"], "EST5EDT,M3.2.0,M11.1.0");
    // Recordings are stored in UTC; reported in device-local time (EDT on Oct 30).
    assert_eq!(cams[0]["earliest"], "2026-10-30T09:00:00");

    let work = tempdir("cli");
    let shot = work.join("cam2.jpg");
    let a = ok_json(run(d, GOOD, &["screenshot", "--channel", "2", "--out", shot.to_str().unwrap()]));
    assert_eq!(a["kind"], "snapshot");
    assert_eq!(probe(&shot)["streams"][0]["codec_name"], "mjpeg", "snapshot is a real, decodable JPEG");

    // Local 10:28-10:37 EDT = 14:28-14:37 UTC; the camera has a 14:30-14:35 gap.
    let window = ["--from", "2026-10-30T10:28:00", "--to", "2026-10-30T10:37:00", "--track", "1"];
    let segs = ok_json(run(d, GOOD, &[&["search"][..], &window[..]].concat()));
    let segs = segs.as_array().unwrap();
    assert_eq!(segs.len(), 2, "{segs:#?}");
    assert_eq!(segs[0]["start_utc"], "2026-10-30T14:28:00");
    assert_eq!(segs[0]["end"], "2026-10-30T10:30:00");
    assert_eq!(segs[1]["start"], "2026-10-30T10:35:00");

    let rec = work.join("rec");
    let dl = [&["download"][..], &window[..], &["--out", rec.to_str().unwrap()][..]].concat();
    let first = ok_json(run(d, GOOD, &dl));
    assert_eq!(first["downloaded"], 2);
    for name in first["files"].as_array().unwrap() {
        let p = rec.join(name.as_str().unwrap());
        let j = probe(&p);
        let codecs: Vec<&str> = j["streams"].as_array().unwrap().iter().map(|s| s["codec_name"].as_str().unwrap()).collect();
        assert_eq!(codecs, ["hevc", "aac"]);
        let dur: f64 = j["format"]["duration"].as_str().unwrap().parse().unwrap();
        assert!((dur - 120.0).abs() < 1.0, "{dur}");
        assert!(decodes_cleanly(&p), "{} does not decode cleanly", p.display());
    }
    let manifest: Value = serde_json::from_slice(&std::fs::read(rec.join("manifest.json")).unwrap()).unwrap();
    assert_eq!(manifest["entries"].as_object().unwrap().len(), 2);

    let s = cam.stats();
    assert_eq!(s.plays.len(), 2);
    assert_eq!(s.plays[0].range, "clock=20261030T142800Z-20261030T143000Z");
    assert_eq!(s.plays[0].rate_control.as_deref(), Some("no"));
    assert_eq!(s.rtsp_without_onvif_replay, 0);
    assert_eq!(s.stale_created, 0, "WS-Security Created must follow the device clock");
    assert_eq!(s.bad_auth, 0);

    // Resume: complete files are verified and kept, nothing is replayed again.
    let second = ok_json(run(d, GOOD, &dl));
    assert_eq!(second["downloaded"], 0);
    assert_eq!(second["skipped_existing"], 2);
    assert_eq!(cam.stats().plays.len(), 2);
}

#[test]
fn long_segments_are_cut_into_chunks() {
    let cam = MockOnvif::start(OnvifConfig::ezviz_two_channel());
    let rec = tempdir("chunks");
    let out = ok_json(run(
        &cam.base_url,
        GOOD,
        &["download", "--from", "2026-10-30T10:35:00", "--to", "2026-10-30T10:45:00", "--track", "1", "--chunk-secs", "240", "--out", rec.to_str().unwrap()],
    ));
    let files: Vec<&str> = out["files"].as_array().unwrap().iter().map(|f| f.as_str().unwrap()).collect();
    assert_eq!(files, ["cam1_20261030T103500_240s.mp4", "cam1_20261030T103900_240s.mp4", "cam1_20261030T104300_120s.mp4"]);
}

#[test]
fn rejected_credential_is_sent_once_and_never_locks_the_account() {
    let cam = MockOnvif::start(OnvifConfig::ezviz_two_channel());
    let out = run(&cam.base_url, "wrong-password-7731", &["list-cameras"]);
    assert_eq!(out.status.code(), Some(77), "{}", String::from_utf8_lossy(&out.stderr));
    let s = cam.stats();
    assert_eq!(s.bad_auth, 1, "the bad credential reached the device more than once");
    assert!(!s.locked);
    ok_json(run(&cam.base_url, GOOD, &["list-cameras"]));
}

#[test]
fn without_find_events_the_recording_span_is_used() {
    let mut cfg = OnvifConfig::ezviz_two_channel();
    cfg.support_find_events = false;
    let cam = MockOnvif::start(cfg);
    let segs = ok_json(run(&cam.base_url, GOOD, &["search", "--from", "2026-10-30T07:00:00", "--to", "2026-10-30T09:30:00", "--track", "1"]));
    let segs = segs.as_array().unwrap();
    assert_eq!(segs.len(), 1);
    // Clipped to EarliestRecording (13:00 UTC = 09:00 EDT).
    assert_eq!(segs[0]["start"], "2026-10-30T09:00:00");
    assert_eq!(segs[0]["end"], "2026-10-30T09:30:00");
}

#[test]
fn tz_rules_that_disagree_with_the_device_fall_back_to_its_offset() {
    let mut cfg = OnvifConfig::ezviz_two_channel();
    // The device claims a local time 1 h off from what its TZ rules imply now.
    cfg.tz = Some("COT5".into());
    cfg.local_offset_secs = Some(-4 * 3600);
    let cam = MockOnvif::start(cfg);
    let info = ok_json(run(&cam.base_url, GOOD, &["device-info"]));
    assert_eq!(info["clock"]["tz_rules_consistent"], false);
    assert_eq!(info["clock"]["utc_offset_secs"], -14400);
}

#[test]
fn dead_route_fails_fast_with_69() {
    let port = std::net::TcpListener::bind("127.0.0.1:0").unwrap().local_addr().unwrap().port();
    let out = run(&format!("http://127.0.0.1:{port}"), GOOD, &["list-cameras"]);
    assert_eq!(out.status.code(), Some(69));
}
