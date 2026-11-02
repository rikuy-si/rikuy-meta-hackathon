//! Mock Ezviz camera speaking ONVIF: Device, Media2 (Profile T), Search and
//! Replay (Profile G), a Digest-protected snapshot URL, and an RTSP server
//! that honours `Require: onvif-replay` + `Range: clock=` and streams real
//! HEVC + AAC over interleaved RTP.
//!
//! Faithful to what matters for the bridge:
//! - WS-Security UsernameToken digest, with `Created` checked against the
//!   *device* clock (which can be skewed, like a camera without NTP);
//! - a POSIX TZ with DST and recordings stored in UTC;
//! - XAddrs and media URIs that carry the camera's own LAN address, not the
//!   one the bridge reaches it at;
//! - account lockout after repeated bad credentials.
use std::collections::HashMap;
use std::io::{BufRead, BufReader, Read, Write};
use std::net::{TcpListener, TcpStream};
use std::sync::{Arc, Mutex};

use base64::Engine;
use chrono::{Duration, NaiveDateTime, Utc};
use sha1::{Digest, Sha1};
use tiny_http::{Request, Server};

use crate::digest::{self, Verdict};
use crate::http::{body, header, hdr, respond};
use crate::media::{fixture, stream_frames};

pub type Range = (NaiveDateTime, NaiveDateTime);

#[derive(Clone)]
pub struct OnvifConfig {
    pub username: String,
    pub password: String,
    pub channel_names: Vec<String>,
    pub tz: Option<String>,
    pub daylight_savings: bool,
    /// LocalDateTime - UTCDateTime the device reports now; None omits LocalDateTime.
    pub local_offset_secs: Option<i64>,
    /// device clock - real clock.
    pub clock_skew_secs: i64,
    /// Recorded UTC ranges per channel.
    pub recordings: Vec<Vec<Range>>,
    pub lockout_after: u32,
    /// The LAN address the camera believes it has (appears in XAddrs/URIs).
    pub reported_host: String,
    pub support_find_events: bool,
}

pub fn utc(s: &str) -> NaiveDateTime {
    NaiveDateTime::parse_from_str(s, "%Y-%m-%dT%H:%M:%S").unwrap()
}

impl OnvifConfig {
    /// Two cameras, US Eastern rules with DST (like the Tejiendo camera's
    /// enabled DST), a 3603 s fast clock, and channel 1 with a 5-minute gap.
    pub fn ezviz_two_channel() -> Self {
        OnvifConfig {
            username: "admin".into(),
            password: "ABCDEF".into(),
            channel_names: vec!["Tejiendo mock".into(), "Bodega mock".into()],
            tz: Some("EST5EDT,M3.2.0,M11.1.0".into()),
            daylight_savings: true,
            local_offset_secs: None,
            clock_skew_secs: 3603,
            recordings: vec![
                vec![(utc("2026-10-30T13:00:00"), utc("2026-10-30T14:30:00")), (utc("2026-10-30T14:35:00"), utc("2026-10-30T16:00:00"))],
                vec![(utc("2026-10-30T12:00:00"), utc("2026-10-30T18:00:00"))],
            ],
            lockout_after: 3,
            reported_host: "192.168.1.64".into(),
            support_find_events: true,
        }
    }
}

#[derive(Debug, Clone, Default)]
pub struct Play {
    pub recording: String,
    pub range: String,
    pub rate_control: Option<String>,
    pub secs: f64,
}

#[derive(Debug, Clone, Default)]
pub struct OnvifStats {
    pub bad_auth: u32,
    pub locked: bool,
    /// Correct digest, but `Created` outside the device's ±5 min window.
    pub stale_created: u32,
    pub actions: Vec<String>,
    pub snapshots: u32,
    pub plays: Vec<Play>,
    pub rtsp_without_onvif_replay: u32,
}

struct State {
    cfg: OnvifConfig,
    stats: OnvifStats,
    http_port: u16,
    rtsp_port: u16,
    event_searches: HashMap<String, (String, NaiveDateTime, NaiveDateTime)>,
    next_search: u32,
    nonce: String,
}

pub struct MockOnvif {
    _server: Arc<Server>,
    state: Arc<Mutex<State>>,
    /// What the bridge is given as the device address.
    pub base_url: String,
    pub rtsp_port: u16,
}

impl MockOnvif {
    pub fn start(cfg: OnvifConfig) -> Self {
        Self::start_on("127.0.0.1:0", "127.0.0.1:0", cfg)
    }

    pub fn start_on(http_addr: &str, rtsp_addr: &str, cfg: OnvifConfig) -> Self {
        let _ = fixture(); // generate media before serving
        let server = Arc::new(Server::http(http_addr).expect("bind mock onvif"));
        let http_port = server.server_addr().to_ip().unwrap().port();
        let rtsp = TcpListener::bind(rtsp_addr).expect("bind mock rtsp");
        let rtsp_port = rtsp.local_addr().unwrap().port();
        let state = Arc::new(Mutex::new(State {
            cfg,
            stats: OnvifStats::default(),
            http_port,
            rtsp_port,
            event_searches: HashMap::new(),
            next_search: 1,
            nonce: format!("{:032x}", Utc::now().timestamp_nanos_opt().unwrap_or(7)),
        }));
        let (s, st) = (server.clone(), state.clone());
        std::thread::spawn(move || {
            for rq in s.incoming_requests() {
                let st = st.clone();
                std::thread::spawn(move || handle_http(rq, &st));
            }
        });
        let st = state.clone();
        std::thread::spawn(move || {
            for conn in rtsp.incoming() {
                let Ok(conn) = conn else { continue };
                let st = st.clone();
                std::thread::spawn(move || {
                    let _ = handle_rtsp(conn, &st);
                });
            }
        });
        MockOnvif { _server: server, state, base_url: format!("http://127.0.0.1:{http_port}"), rtsp_port }
    }

    pub fn stats(&self) -> OnvifStats {
        self.state.lock().unwrap().stats.clone()
    }
}

// ---------------------------------------------------------------- SOAP

/// Text of the first *opening* element with this local name (any prefix).
fn tag<'a>(xml: &'a str, local: &str) -> Option<&'a str> {
    let mut from = 0;
    while let Some(rel) = xml[from..].find('<') {
        let lt = from + rel;
        from = lt + 1;
        let name: String = xml[lt + 1..].chars().take_while(|c| !matches!(c, ' ' | '>' | '/' | '\t' | '\r' | '\n')).collect();
        if name.rsplit(':').next() != Some(local) {
            continue;
        }
        let start = xml[lt..].find('>')? + lt + 1;
        let rest = &xml[start..];
        let end = rest.find("</")?;
        return Some(rest[..end].trim());
    }
    None
}

fn body_action(xml: &str) -> String {
    let Some(b) = xml.find(":Body>").or_else(|| xml.find("<Body>")) else { return String::new() };
    let rest = &xml[b + 6..];
    let Some(lt) = rest.find('<') else { return String::new() };
    let name: String = rest[lt + 1..].chars().take_while(|c| !matches!(c, ' ' | '>' | '/')).collect();
    name.rsplit(':').next().unwrap_or("").to_string()
}

fn envelope(body: &str) -> String {
    format!(
        concat!(
            r#"<?xml version="1.0" encoding="UTF-8"?><env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope" "#,
            r#"xmlns:tt="http://www.onvif.org/ver10/schema" xmlns:tds="http://www.onvif.org/ver10/device/wsdl" "#,
            r#"xmlns:tr2="http://www.onvif.org/ver20/media/wsdl" xmlns:tse="http://www.onvif.org/ver10/search/wsdl" "#,
            r#"xmlns:trp="http://www.onvif.org/ver10/replay/wsdl" xmlns:ter="http://www.onvif.org/ver10/error" "#,
            r#"xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2" xmlns:tns1="http://www.onvif.org/ver10/topics">"#,
            "<env:Body>{}</env:Body></env:Envelope>"
        ),
        body
    )
}

fn fault(sub: &str, reason: &str) -> String {
    envelope(&format!(
        "<env:Fault><env:Code><env:Value>env:Sender</env:Value><env:Subcode><env:Value>ter:{sub}</env:Value></env:Subcode></env:Code><env:Reason><env:Text xml:lang=\"en\">{reason}</env:Text></env:Reason></env:Fault>"
    ))
}

fn xs(t: NaiveDateTime) -> String {
    t.format("%Y-%m-%dT%H:%M:%SZ").to_string()
}

fn parse_xs(s: &str) -> Option<NaiveDateTime> {
    chrono::DateTime::parse_from_rfc3339(s.trim()).ok().map(|d| d.naive_utc())
}

fn onvif_dt(t: NaiveDateTime) -> String {
    use chrono::{Datelike, Timelike};
    format!(
        "<tt:Time><tt:Hour>{}</tt:Hour><tt:Minute>{}</tt:Minute><tt:Second>{}</tt:Second></tt:Time><tt:Date><tt:Year>{}</tt:Year><tt:Month>{}</tt:Month><tt:Day>{}</tt:Day></tt:Date>",
        t.hour(), t.minute(), t.second(), t.year(), t.month(), t.day()
    )
}

enum Auth {
    Ok,
    Missing,
    Bad,
    Stale,
    Locked,
}

fn check_wsse(xml: &str, st: &mut State) -> Auth {
    if st.stats.locked {
        return Auth::Locked;
    }
    let (Some(user), Some(pass), Some(nonce), Some(created)) =
        (tag(xml, "Username"), tag(xml, "Password"), tag(xml, "Nonce"), tag(xml, "Created"))
    else {
        return Auth::Missing;
    };
    let Ok(nonce_raw) = base64::engine::general_purpose::STANDARD.decode(nonce) else { return Auth::Bad };
    let mut h = Sha1::new();
    h.update(&nonce_raw);
    h.update(created.as_bytes());
    h.update(st.cfg.password.as_bytes());
    let expected = base64::engine::general_purpose::STANDARD.encode(h.finalize());
    if std::env::var_os("RIKUY_MOCK_DEBUG").is_some() {
        eprintln!("mock-onvif: wsse user={user} created={created} nonce={nonce} got={pass} want={expected}");
    }
    if user != st.cfg.username || pass != expected {
        st.stats.bad_auth += 1;
        if st.stats.bad_auth >= st.cfg.lockout_after {
            st.stats.locked = true;
        }
        return Auth::Bad;
    }
    let device_now = Utc::now().naive_utc() + Duration::seconds(st.cfg.clock_skew_secs);
    match parse_xs(created) {
        Some(c) if (c - device_now).num_seconds().abs() <= 300 => Auth::Ok,
        _ => {
            st.stats.stale_created += 1;
            Auth::Stale
        }
    }
}

fn handle_http(mut rq: Request, st: &Arc<Mutex<State>>) {
    let url = rq.url().to_string();
    if rq.method().as_str() == "GET" && url.starts_with("/onvif/snapshot/") {
        return snapshot(rq, st);
    }
    let xml = String::from_utf8_lossy(&body(&mut rq)).to_string();
    let action = body_action(&xml);
    let mut s = st.lock().unwrap();
    s.stats.actions.push(action.clone());
    if action != "GetSystemDateAndTime" {
        let verdict = check_wsse(&xml, &mut s);
        let msg = match verdict {
            Auth::Ok => None,
            Auth::Missing => Some("Sender not authorized: missing WS-Security"),
            Auth::Bad => Some("Sender not authorized"),
            Auth::Stale => Some("Sender not authorized: Created out of range"),
            Auth::Locked => Some("Account locked"),
        };
        if let Some(m) = msg {
            if std::env::var_os("RIKUY_MOCK_DEBUG").is_some() {
                eprintln!("mock-onvif: {action}: {m}");
            }
            return respond(rq, 400, "application/soap+xml", fault("NotAuthorized", m).into_bytes(), vec![]);
        }
    }
    let base = format!("http://{}:{}", s.cfg.reported_host, s.http_port);
    let reply = match action.as_str() {
        "GetSystemDateAndTime" => {
            let now = Utc::now().naive_utc() + Duration::seconds(s.cfg.clock_skew_secs);
            let tz = s.cfg.tz.as_ref().map(|t| format!("<tt:TimeZone><tt:TZ>{t}</tt:TZ></tt:TimeZone>")).unwrap_or_default();
            let local = s
                .cfg
                .local_offset_secs
                .map(|o| format!("<tt:LocalDateTime>{}</tt:LocalDateTime>", onvif_dt(now + Duration::seconds(o))))
                .unwrap_or_default();
            Ok(format!(
                "<tds:GetSystemDateAndTimeResponse><tds:SystemDateAndTime><tt:DateTimeType>Manual</tt:DateTimeType><tt:DaylightSavings>{}</tt:DaylightSavings>{tz}<tt:UTCDateTime>{}</tt:UTCDateTime>{local}</tds:SystemDateAndTime></tds:GetSystemDateAndTimeResponse>",
                s.cfg.daylight_savings,
                onvif_dt(now)
            ))
        }
        "GetDeviceInformation" => Ok(
            "<tds:GetDeviceInformationResponse><tds:Manufacturer>EZVIZ</tds:Manufacturer><tds:Model>CS-C6-MOCK</tds:Model><tds:FirmwareVersion>V5.3.8 build 230601</tds:FirmwareVersion><tds:SerialNumber>MOCK00001</tds:SerialNumber><tds:HardwareId>mock</tds:HardwareId></tds:GetDeviceInformationResponse>".to_string(),
        ),
        "GetServices" => {
            let svc = |ns: &str, path: &str| format!("<tds:Service><tds:Namespace>{ns}</tds:Namespace><tds:XAddr>{base}{path}</tds:XAddr><tds:Version><tt:Major>2</tt:Major><tt:Minor>60</tt:Minor></tds:Version></tds:Service>");
            Ok(format!(
                "<tds:GetServicesResponse>{}{}{}{}</tds:GetServicesResponse>",
                svc("http://www.onvif.org/ver10/device/wsdl", "/onvif/device_service"),
                svc("http://www.onvif.org/ver20/media/wsdl", "/onvif/media2_service"),
                svc("http://www.onvif.org/ver10/search/wsdl", "/onvif/search_service"),
                svc("http://www.onvif.org/ver10/replay/wsdl", "/onvif/replay_service"),
            ))
        }
        "GetProfiles" => {
            let mut p = String::new();
            for i in 1..=s.cfg.channel_names.len() {
                for (kind, enc, w, h) in [("sub", "H264", 640, 360), ("main", "H265", 2880, 1620)] {
                    p.push_str(&format!(
                        "<tr2:Profiles token=\"Profile_{i}_{kind}\" fixed=\"true\"><tr2:Name>{kind}Stream</tr2:Name><tr2:Configurations><tr2:VideoSource token=\"VSC_{i}\"><tt:Name>VSC_{i}</tt:Name><tt:SourceToken>VideoSource_{i}</tt:SourceToken></tr2:VideoSource><tr2:VideoEncoder token=\"VE_{i}_{kind}\"><tt:Name>VE</tt:Name><tt:Encoding>{enc}</tt:Encoding><tt:Resolution><tt:Width>{w}</tt:Width><tt:Height>{h}</tt:Height></tt:Resolution></tr2:VideoEncoder></tr2:Configurations></tr2:Profiles>"
                    ));
                }
            }
            Ok(format!("<tr2:GetProfilesResponse>{p}</tr2:GetProfilesResponse>"))
        }
        "GetSnapshotUri" => match tag(&xml, "ProfileToken") {
            Some(t) if t.starts_with("Profile_") => Ok(format!("<tr2:GetSnapshotUriResponse><tr2:Uri>{base}/onvif/snapshot/{t}.jpg</tr2:Uri></tr2:GetSnapshotUriResponse>")),
            _ => Err(("InvalidArgVal", "no such profile")),
        },
        "FindRecordings" => Ok("<tse:FindRecordingsResponse><tse:SearchToken>rec-search-1</tse:SearchToken></tse:FindRecordingsResponse>".into()),
        "GetRecordingSearchResults" => {
            let mut r = String::new();
            for (i, ranges) in s.cfg.recordings.iter().enumerate() {
                let i = i + 1;
                let (Some(first), Some(last)) = (ranges.first(), ranges.last()) else { continue };
                r.push_str(&format!(
                    "<tt:RecordingInformation><tt:RecordingToken>Recording_{i}</tt:RecordingToken><tt:Source><tt:SourceId>VideoSource_{i}</tt:SourceId><tt:Name>{}</tt:Name><tt:Location>mock</tt:Location><tt:Description/><tt:Address/></tt:Source><tt:EarliestRecording>{}</tt:EarliestRecording><tt:LatestRecording>{}</tt:LatestRecording><tt:Content/><tt:Track><tt:TrackToken>VideoTrack_{i}</tt:TrackToken><tt:TrackType>Video</tt:TrackType><tt:Description/></tt:Track><tt:Track><tt:TrackToken>AudioTrack_{i}</tt:TrackToken><tt:TrackType>Audio</tt:TrackType><tt:Description/></tt:Track><tt:RecordingStatus>Stopped</tt:RecordingStatus></tt:RecordingInformation>",
                    s.cfg.channel_names.get(i - 1).cloned().unwrap_or_default(),
                    xs(first.0),
                    xs(last.1)
                ));
            }
            Ok(format!("<tse:GetRecordingSearchResultsResponse><tse:ResultList><tt:SearchState>Completed</tt:SearchState>{r}</tse:ResultList></tse:GetRecordingSearchResultsResponse>"))
        }
        "FindEvents" if !s.cfg.support_find_events => Err(("ActionNotSupported", "FindEvents not supported")),
        "FindEvents" => match (tag(&xml, "StartPoint").and_then(parse_xs), tag(&xml, "EndPoint").and_then(parse_xs), tag(&xml, "IncludedRecordings")) {
            (Some(a), Some(b), Some(r)) => {
                let tok = format!("ev-search-{}", s.next_search);
                s.next_search += 1;
                s.event_searches.insert(tok.clone(), (r.to_string(), a, b));
                Ok(format!("<tse:FindEventsResponse><tse:SearchToken>{tok}</tse:SearchToken></tse:FindEventsResponse>"))
            }
            _ => Err(("InvalidArgVal", "FindEvents needs StartPoint, EndPoint and IncludedRecordings")),
        },
        "GetEventSearchResults" => match tag(&xml, "SearchToken").and_then(|t| s.event_searches.get(t).cloned()) {
            Some((rec, a, b)) => {
                let idx: usize = rec.trim_start_matches("Recording_").parse().unwrap_or(0);
                let ranges = s.cfg.recordings.get(idx.wrapping_sub(1)).cloned().unwrap_or_default();
                let ev = |t: NaiveDateTime, present: bool, start: bool| {
                    format!(
                        "<tt:Result><tt:RecordingToken>{rec}</tt:RecordingToken><tt:TrackToken>VideoTrack_{idx}</tt:TrackToken><tt:Time>{}</tt:Time><tt:Event><wsnt:Topic Dialect=\"http://www.onvif.org/ver10/tev/topicExpression/ConcreteSet\">tns1:RecordingHistory/Track/State</wsnt:Topic><wsnt:Message><tt:Message UtcTime=\"{}\"><tt:Source><tt:SimpleItem Name=\"Track\" Value=\"VideoTrack_{idx}\"/></tt:Source><tt:Data><tt:SimpleItem Name=\"IsDataPresent\" Value=\"{present}\"/></tt:Data></tt:Message></wsnt:Message></tt:Event><tt:StartStateEvent>{start}</tt:StartStateEvent></tt:Result>",
                        xs(t), xs(t)
                    )
                };
                let inside = ranges.iter().any(|(s0, e0)| a >= *s0 && a < *e0);
                let mut out = ev(a, inside, true);
                for (s0, e0) in &ranges {
                    if *s0 > a && *s0 <= b {
                        out.push_str(&ev(*s0, true, false));
                    }
                    if *e0 > a && *e0 <= b {
                        out.push_str(&ev(*e0, false, false));
                    }
                }
                Ok(format!("<tse:GetEventSearchResultsResponse><tse:ResultList><tt:SearchState>Completed</tt:SearchState>{out}</tse:ResultList></tse:GetEventSearchResultsResponse>"))
            }
            None => Err(("InvalidToken", "unknown search token")),
        },
        "EndSearch" => Ok(format!("<tse:EndSearchResponse><tse:Endpoint>{}</tse:Endpoint></tse:EndSearchResponse>", xs(Utc::now().naive_utc()))),
        "GetReplayUri" => match tag(&xml, "RecordingToken") {
            Some(t) if t.starts_with("Recording_") => Ok(format!(
                "<trp:GetReplayUriResponse><trp:Uri>rtsp://{}:{}/replay/{t}</trp:Uri></trp:GetReplayUriResponse>",
                s.cfg.reported_host, s.rtsp_port
            )),
            _ => Err(("InvalidArgVal", "no such recording")),
        },
        _ => Err(("ActionNotSupported", "action not supported by the mock")),
    };
    drop(s);
    match reply {
        Ok(b) => respond(rq, 200, "application/soap+xml; charset=utf-8", envelope(&b).into_bytes(), vec![]),
        Err((sub, reason)) => respond(rq, 400, "application/soap+xml", fault(sub, reason).into_bytes(), vec![]),
    }
}

fn snapshot(rq: Request, st: &Arc<Mutex<State>>) {
    let uri = rq.url().to_string();
    let mut s = st.lock().unwrap();
    let challenge = format!("Digest realm=\"EZVIZ-MOCK\", qop=\"auth\", nonce=\"{}\"", s.nonce);
    if s.stats.locked {
        drop(s);
        return respond(rq, 401, "text/plain", b"locked".to_vec(), vec![hdr("WWW-Authenticate", &challenge)]);
    }
    let Some(auth) = header(&rq, "Authorization") else {
        drop(s);
        return respond(rq, 401, "text/plain", vec![], vec![hdr("WWW-Authenticate", &challenge)]);
    };
    let (user, pass, nonce) = (s.cfg.username.clone(), s.cfg.password.clone(), s.nonce.clone());
    match digest::verify(&auth, "GET", &uri, &user, &pass, "EZVIZ-MOCK", &nonce) {
        Verdict::Ok => {
            s.stats.snapshots += 1;
            drop(s);
            respond(rq, 200, "image/jpeg", fixture().jpeg.clone(), vec![])
        }
        Verdict::Stale => {
            drop(s);
            respond(rq, 401, "text/plain", vec![], vec![hdr("WWW-Authenticate", &format!("{challenge}, stale=true"))])
        }
        Verdict::Bad => {
            s.stats.bad_auth += 1;
            if s.stats.bad_auth >= s.cfg.lockout_after {
                s.stats.locked = true;
            }
            drop(s);
            respond(rq, 401, "text/plain", vec![], vec![hdr("WWW-Authenticate", &challenge)])
        }
    }
}

// ---------------------------------------------------------------- RTSP

struct Rq {
    method: String,
    uri: String,
    headers: Vec<(String, String)>,
}

impl Rq {
    fn h(&self, k: &str) -> Option<&str> {
        self.headers.iter().find(|(a, _)| a.eq_ignore_ascii_case(k)).map(|(_, v)| v.as_str())
    }
}

fn read_rq(r: &mut impl BufRead) -> Option<Rq> {
    let mut start = String::new();
    loop {
        start.clear();
        if r.read_line(&mut start).ok()? == 0 {
            return None;
        }
        if !start.trim().is_empty() {
            break;
        }
    }
    let mut parts = start.split_whitespace();
    let (method, uri) = (parts.next()?.to_string(), parts.next()?.to_string());
    let mut headers = vec![];
    loop {
        let mut l = String::new();
        if r.read_line(&mut l).ok()? == 0 {
            return None;
        }
        let l = l.trim_end();
        if l.is_empty() {
            break;
        }
        if let Some((k, v)) = l.split_once(':') {
            headers.push((k.trim().to_string(), v.trim().to_string()));
        }
    }
    let len: usize = headers.iter().find(|(k, _)| k.eq_ignore_ascii_case("Content-Length")).and_then(|(_, v)| v.parse().ok()).unwrap_or(0);
    let mut b = vec![0; len];
    r.read_exact(&mut b).ok()?;
    Some(Rq { method, uri, headers })
}

fn reply(w: &mut impl Write, code: u16, reason: &str, cseq: &str, extra: &[(&str, String)], body: &str) -> std::io::Result<()> {
    let mut s = format!("RTSP/1.0 {code} {reason}\r\nCSeq: {cseq}\r\nServer: Rikuy-Mock-ONVIF\r\n");
    for (k, v) in extra {
        s.push_str(&format!("{k}: {v}\r\n"));
    }
    if !body.is_empty() {
        s.push_str(&format!("Content-Length: {}\r\n", body.len()));
    }
    s.push_str("\r\n");
    s.push_str(body);
    w.write_all(s.as_bytes())?;
    w.flush()
}

fn parse_clock(range: &str) -> Option<(NaiveDateTime, Option<NaiveDateTime>)> {
    let v = range.trim().strip_prefix("clock=")?;
    let (a, b) = v.split_once('-')?;
    let p = |s: &str| {
        let s = s.trim().trim_end_matches('Z');
        let s = s.split('.').next().unwrap_or(s);
        NaiveDateTime::parse_from_str(s, "%Y%m%dT%H%M%S").ok()
    };
    Some((p(a)?, if b.trim().is_empty() { None } else { Some(p(b)?) }))
}

fn handle_rtsp(conn: TcpStream, st: &Arc<Mutex<State>>) -> std::io::Result<()> {
    let mut r = BufReader::new(conn.try_clone()?);
    let mut w = conn;
    let mut channels: Vec<(u32, u8)> = vec![]; // (track id, interleaved channel)
    let mut require_ok = true;
    loop {
        let Some(rq) = read_rq(&mut r) else { return Ok(()) };
        let cseq = rq.h("CSeq").unwrap_or("0").to_string();
        if rq.method == "OPTIONS" {
            reply(&mut w, 200, "OK", &cseq, &[("Public", "OPTIONS, DESCRIBE, SETUP, PLAY, TEARDOWN, GET_PARAMETER".into())], "")?;
            continue;
        }
        if rq.method == "TEARDOWN" || rq.method == "GET_PARAMETER" {
            reply(&mut w, 200, "OK", &cseq, &[], "")?;
            if rq.method == "TEARDOWN" {
                return Ok(());
            }
            continue;
        }
        // Digest on every other method, against the same account as SOAP.
        {
            let mut s = st.lock().unwrap();
            let challenge = format!("Digest realm=\"EZVIZ-MOCK\", qop=\"auth\", nonce=\"{}\"", s.nonce);
            let verdict = match (s.stats.locked, rq.h("Authorization")) {
                (true, _) => Some(false),
                (false, None) => None,
                (false, Some(a)) => {
                    let (u, p, n) = (s.cfg.username.clone(), s.cfg.password.clone(), s.nonce.clone());
                    Some(matches!(digest::verify(a, &rq.method, &rq.uri, &u, &p, "EZVIZ-MOCK", &n), Verdict::Ok))
                }
            };
            match verdict {
                Some(true) => {}
                Some(false) => {
                    if !s.stats.locked {
                        s.stats.bad_auth += 1;
                        if s.stats.bad_auth >= s.cfg.lockout_after {
                            s.stats.locked = true;
                        }
                    }
                    drop(s);
                    reply(&mut w, 401, "Unauthorized", &cseq, &[("WWW-Authenticate", challenge)], "")?;
                    continue;
                }
                None => {
                    drop(s);
                    reply(&mut w, 401, "Unauthorized", &cseq, &[("WWW-Authenticate", challenge)], "")?;
                    continue;
                }
            }
        }
        let path = rq.uri.splitn(4, '/').nth(3).map(|p| format!("/{p}")).unwrap_or_default();
        let recording = path.trim_start_matches("/replay/").split('/').next().unwrap_or("").to_string();
        let (ranges, host, port) = {
            let s = st.lock().unwrap();
            let idx: usize = recording.trim_start_matches("Recording_").parse().unwrap_or(0);
            (s.cfg.recordings.get(idx.wrapping_sub(1)).cloned(), s.cfg.reported_host.clone(), s.rtsp_port)
        };
        let Some(ranges) = ranges.filter(|_| path.starts_with("/replay/Recording_")) else {
            reply(&mut w, 404, "Not Found", &cseq, &[], "")?;
            continue;
        };
        let has_replay = rq.h("Require").map(|v| v.split(',').any(|x| x.trim() == "onvif-replay")).unwrap_or(false);
        match rq.method.as_str() {
            "DESCRIBE" => {
                let base = format!("rtsp://{host}:{port}/replay/{recording}/");
                let sdp = fixture().sdp(&base);
                reply(&mut w, 200, "OK", &cseq, &[("Content-Base", base.clone()), ("Content-Type", "application/sdp".into())], &sdp)?;
            }
            "SETUP" => {
                if !has_replay {
                    st.lock().unwrap().stats.rtsp_without_onvif_replay += 1;
                    require_ok = false;
                    reply(&mut w, 551, "Option not supported", &cseq, &[("Unsupported", "onvif-replay".into())], "")?;
                    continue;
                }
                let transport = rq.h("Transport").unwrap_or("").to_string();
                let il = transport.split(';').find_map(|p| p.strip_prefix("interleaved=")).and_then(|v| v.split('-').next()).and_then(|v| v.parse::<u8>().ok());
                let (Some(ch), true) = (il, transport.contains("TCP")) else {
                    reply(&mut w, 461, "Unsupported Transport", &cseq, &[], "")?;
                    continue;
                };
                let track: u32 = if rq.uri.ends_with("trackID=1") { 1 } else { 0 };
                channels.push((track, ch));
                reply(&mut w, 200, "OK", &cseq, &[("Transport", transport), ("Session", "4D0C1A2B;timeout=60".into())], "")?;
            }
            "PLAY" => {
                if !has_replay || !require_ok {
                    st.lock().unwrap().stats.rtsp_without_onvif_replay += 1;
                    reply(&mut w, 551, "Option not supported", &cseq, &[("Unsupported", "onvif-replay".into())], "")?;
                    continue;
                }
                let Some((a, b)) = rq.h("Range").and_then(parse_clock) else {
                    reply(&mut w, 457, "Invalid Range", &cseq, &[], "")?;
                    continue;
                };
                let Some(&(_, rend)) = ranges.iter().find(|(s0, e0)| a >= *s0 && a < *e0) else {
                    reply(&mut w, 457, "Invalid Range", &cseq, &[], "")?;
                    continue;
                };
                let end = b.unwrap_or(rend).min(rend).min(a + Duration::hours(1));
                let secs = (end - a).num_milliseconds() as f64 / 1000.0;
                st.lock().unwrap().stats.plays.push(Play {
                    recording: recording.clone(),
                    range: rq.h("Range").unwrap_or("").to_string(),
                    rate_control: rq.h("Rate-Control").map(String::from),
                    secs,
                });
                reply(
                    &mut w,
                    200,
                    "OK",
                    &cseq,
                    &[("Session", "4D0C1A2B".into()), ("Range", rq.h("Range").unwrap_or("").to_string())],
                    "",
                )?;
                let vch = channels.iter().find(|(t, _)| *t == 0).map(|(_, c)| *c).unwrap_or(0);
                let ach = channels.iter().find(|(t, _)| *t == 1).map(|(_, c)| *c);
                let mut bw = std::io::BufWriter::with_capacity(256 * 1024, w.try_clone()?);
                stream_frames(fixture(), secs, vch, ach, |frame| bw.write_all(frame).is_ok());
                let _ = bw.flush();
                drop(bw);
                // End of the requested range: close, like a camera ending replay.
                let _ = w.shutdown(std::net::Shutdown::Write);
                // Drain whatever the client still sends until it hangs up.
                let mut sink = [0u8; 4096];
                while matches!(r.read(&mut sink), Ok(n) if n > 0) {}
                return Ok(());
            }
            _ => reply(&mut w, 405, "Method Not Allowed", &cseq, &[], "")?,
        }
    }
}

#[cfg(test)]
mod tests {
    #[test]
    fn tag_extracts_wsse_fields() {
        let x = r#"<s:Header><wsse:Security s:mustUnderstand="1"><wsse:UsernameToken><wsse:Username>admin</wsse:Username><wsse:Password Type="http://x#PasswordDigest">abc=</wsse:Password><wsse:Nonce EncodingType="http://y#Base64Binary">bm9uY2U=</wsse:Nonce><wsu:Created>2026-11-02T15:00:00.000Z</wsu:Created></wsse:UsernameToken></wsse:Security></s:Header>"#;
        assert_eq!(super::tag(x, "Username"), Some("admin"));
        assert_eq!(super::tag(x, "Password"), Some("abc="));
        assert_eq!(super::tag(x, "Nonce"), Some("bm9uY2U="));
        assert_eq!(super::tag(x, "Created"), Some("2026-11-02T15:00:00.000Z"));
    }
}
