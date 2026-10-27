use chrono::NaiveDate;
use rikuy_bridge_common::{BridgeError, Credential, Secret};
use rikuy_bridge_hikvision::IsapiClient;
use rikuy_bridge_mocks::isapi::{IsapiConfig, MockIsapi};

fn cred(pass: &str) -> Credential {
    Credential { username: "admin".into(), password: Secret::new(pass) }
}

fn day(h: u32) -> chrono::NaiveDateTime {
    NaiveDate::from_ymd_opt(2026, 10, 29).unwrap().and_hms_opt(h, 0, 0).unwrap()
}

#[test]
fn lists_all_eight_tracks() {
    let dvr = MockIsapi::start(IsapiConfig::eight_channel_dvr(2));
    let mut c = IsapiClient::new(&dvr.base_url, cred("correct-horse")).unwrap();
    let tracks = c.tracks().unwrap();
    assert_eq!(tracks.iter().map(|t| t.id).collect::<Vec<_>>(), vec![101, 201, 301, 401, 501, 601, 701, 801]);
    assert_eq!(tracks[3].channel, 4);
}

#[test]
fn search_paginates_past_the_64_cap() {
    // 4 recording cameras x 96 clips of 15 min = 384 clips over 24 h.
    let dvr = MockIsapi::start(IsapiConfig::eight_channel_dvr(96));
    let mut c = IsapiClient::new(&dvr.base_url, cred("correct-horse")).unwrap();
    let recs = c.search(day(5), day(5) + chrono::Duration::hours(24), &[]).unwrap();
    assert_eq!(recs.len(), 384);
    let searches = dvr.stats().requests.iter().filter(|(_, p)| p == "/ISAPI/ContentMgmt/search").count();
    // 384 / 64 = 6 pages (+ the unauthenticated first request on the very first call).
    assert!(searches >= 6 && searches <= 7, "search requests: {searches}");
    assert!(recs.iter().all(|r| r.size.is_some() && r.name.is_some()));
    // Tracks without recordings return nothing; timestamps stay local.
    assert!(recs.iter().all(|r| [101, 201, 301, 401].contains(&r.track)));
    assert_eq!(recs[0].start, day(5));
}

#[test]
fn search_filters_by_track_and_window() {
    let dvr = MockIsapi::start(IsapiConfig::eight_channel_dvr(96));
    let mut c = IsapiClient::new(&dvr.base_url, cred("correct-horse")).unwrap();
    let recs = c.search(day(6), day(7), &[201]).unwrap();
    assert_eq!(recs.len(), 4);
    assert!(recs.iter().all(|r| r.track == 201));
}

#[test]
fn reuses_digest_session_and_survives_stale_nonce() {
    let mut cfg = IsapiConfig::eight_channel_dvr(96);
    cfg.nonce_ttl = Some(2);
    let dvr = MockIsapi::start(cfg);
    let mut c = IsapiClient::new(&dvr.base_url, cred("correct-horse")).unwrap();
    let recs = c.search(day(5), day(5) + chrono::Duration::hours(24), &[]).unwrap();
    assert_eq!(recs.len(), 384);
    let s = dvr.stats();
    assert!(s.stale_challenges > 0, "nonce should have rotated");
    assert_eq!(s.bad_auth, 0);
    assert!(!s.locked);
}

#[test]
fn wrong_password_is_rejected_after_one_credentialed_attempt() {
    let dvr = MockIsapi::start(IsapiConfig::eight_channel_dvr(2));
    let mut c = IsapiClient::new(&dvr.base_url, cred("wrong")).unwrap();
    let err = c.tracks().unwrap_err();
    assert!(matches!(err, BridgeError::AuthRejected { status: 401 }), "{err:?}");
    // Further calls never reach the device.
    let before = dvr.stats().requests.len();
    assert!(matches!(c.search(day(5), day(6), &[]), Err(BridgeError::AuthRejected { .. })));
    let s = dvr.stats();
    assert_eq!(s.requests.len(), before);
    assert_eq!(s.bad_auth, 1);
    assert!(!s.locked, "one bad attempt must not lock the account");
}
