//! Mock Hikvision DVR speaking ISAPI.
use std::sync::{Arc, Mutex};
use std::thread::JoinHandle;

use chrono::{Duration, NaiveDate, NaiveDateTime};
use tiny_http::{Request, Server};

use crate::digest::{self, Verdict};
use crate::http::{body, header, hdr, respond};

pub const IMKH_HEADER_LEN: usize = 40;
pub const DVR_PAGE_CAP: usize = 64;
const TS: &str = "%Y-%m-%dT%H:%M:%SZ";
const TS_COMPACT: &str = "%Y%m%dT%H%M%SZ";

#[derive(Debug, Clone)]
pub struct Clip {
    pub track: u32,
    pub start: NaiveDateTime,
    pub end: NaiveDateTime,
    pub name: String,
    pub size: u64,
}

impl Clip {
    pub fn playback_uri(&self, host: &str) -> String {
        format!(
            "rtsp://{host}/Streaming/tracks/{}/?starttime={}&endtime={}&name={}&size={}",
            self.track,
            self.start.format(TS_COMPACT),
            self.end.format(TS_COMPACT),
            self.name,
            self.size
        )
    }
}

#[derive(Debug, Clone)]
pub struct IsapiConfig {
    pub username: String,
    pub password: String,
    pub realm: String,
    /// All tracks the DVR reports (e.g. 8 channels: 101..801).
    pub tracks: Vec<u32>,
    pub clips: Vec<Clip>,
    pub page_cap: usize,
    /// Bad Digest responses tolerated before the account locks.
    pub lockout_after: u32,
    /// Rotate the nonce after this many authenticated requests (stale=true).
    pub nonce_ttl: Option<u32>,
}

impl IsapiConfig {
    /// An 8-channel DVR where only cameras 1-4 record, `clips_per_track` clips
    /// of 15 minutes each starting at 2026-10-29 05:00 local.
    pub fn eight_channel_dvr(clips_per_track: usize) -> Self {
        let day = NaiveDate::from_ymd_opt(2026, 10, 29).unwrap().and_hms_opt(5, 0, 0).unwrap();
        let mut clips = Vec::new();
        let mut serial = 47_000_000u64;
        for track in [101u32, 201, 301, 401] {
            for i in 0..clips_per_track {
                let start = day + Duration::minutes(15 * i as i64);
                serial += 1;
                clips.push(Clip {
                    track,
                    start,
                    end: start + Duration::minutes(15),
                    name: format!("{serial:017}"),
                    size: 1024 + ((i as u64 * 37 + track as u64) % 512),
                });
            }
        }
        IsapiConfig {
            username: "admin".into(),
            password: "correct-horse".into(),
            realm: "DS-7108HGHI-F1".into(),
            tracks: (1..=8).map(|c| c * 100 + 1).collect(),
            clips,
            page_cap: DVR_PAGE_CAP,
            lockout_after: 3,
            nonce_ttl: None,
        }
    }
}

#[derive(Debug, Default, Clone)]
pub struct IsapiStats {
    /// (method, path) of every request received.
    pub requests: Vec<(String, String)>,
    /// Requests carrying an Authorization header that failed verification.
    pub bad_auth: u32,
    pub locked: bool,
    pub get_download_hits: u32,
    pub stale_challenges: u32,
}

struct State {
    cfg: IsapiConfig,
    stats: IsapiStats,
    nonce: String,
    nonce_uses: u32,
    nonce_gen: u32,
}

pub struct MockIsapi {
    server: Arc<Server>,
    state: Arc<Mutex<State>>,
    handle: Option<JoinHandle<()>>,
    pub base_url: String,
}

impl MockIsapi {
    pub fn start(cfg: IsapiConfig) -> Self {
        Self::start_on("127.0.0.1:0", cfg)
    }

    pub fn start_on(addr: &str, cfg: IsapiConfig) -> Self {
        let server = Arc::new(Server::http(addr).expect("bind mock isapi"));
        let base_url = format!("http://{}", server.server_addr().to_ip().unwrap());
        let state = Arc::new(Mutex::new(State {
            cfg,
            stats: IsapiStats::default(),
            nonce: "nonce-0".into(),
            nonce_uses: 0,
            nonce_gen: 0,
        }));
        let (s, st) = (server.clone(), state.clone());
        let handle = std::thread::spawn(move || {
            for rq in s.incoming_requests() {
                handle_request(rq, &st);
            }
        });
        MockIsapi { server, state, handle: Some(handle), base_url }
    }

    pub fn stats(&self) -> IsapiStats {
        self.state.lock().unwrap().stats.clone()
    }

    pub fn clips(&self) -> Vec<Clip> {
        self.state.lock().unwrap().cfg.clips.clone()
    }

    pub fn host(&self) -> String {
        self.base_url.trim_start_matches("http://").to_string()
    }
}

impl Drop for MockIsapi {
    fn drop(&mut self) {
        self.server.unblock();
        if let Some(h) = self.handle.take() {
            let _ = h.join();
        }
    }
}

fn challenge(rq: Request, st: &mut State, stale: bool) {
    let value = format!(
        "Digest realm=\"{}\", qop=\"auth\", nonce=\"{}\", opaque=\"mock-opaque\"{}",
        st.cfg.realm,
        st.nonce,
        if stale { ", stale=\"true\"" } else { "" }
    );
    respond(rq, 401, "application/xml", status_xml(401, "Unauthorized"), vec![hdr("WWW-Authenticate", &value)]);
}

fn status_xml(code: u16, msg: &str) -> Vec<u8> {
    format!(
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<ResponseStatus version=\"1.0\" xmlns=\"http://www.hikvision.com/ver20/XMLSchema\">\n<requestURL></requestURL>\n<statusCode>{code}</statusCode>\n<statusString>{msg}</statusString>\n</ResponseStatus>\n"
    )
    .into_bytes()
}

fn handle_request(mut rq: Request, state: &Arc<Mutex<State>>) {
    let mut st = state.lock().unwrap();
    let method = rq.method().as_str().to_string();
    let url = rq.url().to_string();
    let path = url.split('?').next().unwrap_or("").to_string();
    st.stats.requests.push((method.clone(), path.clone()));

    // --- authentication ---
    let Some(auth) = header(&rq, "Authorization") else {
        return challenge(rq, &mut st, false);
    };
    if st.stats.locked {
        return challenge(rq, &mut st, false);
    }
    let (user, pass, realm, nonce) =
        (st.cfg.username.clone(), st.cfg.password.clone(), st.cfg.realm.clone(), st.nonce.clone());
    match digest::verify(&auth, &method, &url, &user, &pass, &realm, &nonce) {
        Verdict::Ok => {}
        Verdict::Stale => {
            st.stats.stale_challenges += 1;
            return challenge(rq, &mut st, true);
        }
        Verdict::Bad => {
            st.stats.bad_auth += 1;
            if st.stats.bad_auth >= st.cfg.lockout_after {
                st.stats.locked = true;
            }
            return challenge(rq, &mut st, false);
        }
    }
    st.nonce_uses += 1;
    if let Some(ttl) = st.cfg.nonce_ttl {
        if st.nonce_uses >= ttl {
            st.nonce_gen += 1;
            st.nonce = format!("nonce-{}", st.nonce_gen);
            st.nonce_uses = 0;
        }
    }

    // --- routing ---
    match (method.as_str(), path.as_str()) {
        ("GET", "/ISAPI/ContentMgmt/record/tracks") => {
            let xml = tracks_xml(&st.cfg);
            respond(rq, 200, "application/xml", xml.into_bytes(), vec![]);
        }
        ("POST", "/ISAPI/ContentMgmt/search") => {
            let req = String::from_utf8_lossy(&body(&mut rq)).to_string();
            let host = rq.headers().iter().find(|h| h.field.equiv("Host")).map(|h| h.value.to_string()).unwrap_or_default();
            match search_xml(&st.cfg, &req, &host) {
                Some(xml) => respond(rq, 200, "application/xml", xml.into_bytes(), vec![]),
                None => respond(rq, 400, "application/xml", status_xml(400, "Invalid XML Content"), vec![]),
            }
        }
        ("GET", "/ISAPI/ContentMgmt/download") => {
            st.stats.get_download_hits += 1;
            respond(rq, 400, "application/xml", status_xml(400, "Invalid Operation"), vec![]);
        }
        ("POST", "/ISAPI/ContentMgmt/download") => {
            let req = String::from_utf8_lossy(&body(&mut rq)).to_string();
            match download_payload(&st.cfg, &req) {
                Some(bytes) => respond(rq, 200, "application/octet-stream", bytes, vec![]),
                None => respond(rq, 404, "application/xml", status_xml(404, "Not Found"), vec![]),
            }
        }
        ("GET", p) if p.starts_with("/ISAPI/Streaming/channels/") && p.ends_with("/picture") => {
            let id: u32 = p
                .trim_start_matches("/ISAPI/Streaming/channels/")
                .trim_end_matches("/picture")
                .parse()
                .unwrap_or(0);
            if st.cfg.tracks.contains(&(id / 100 * 100 + 1)) && matches!(id % 100, 1 | 2) {
                respond(rq, 200, "image/jpeg", fake_jpeg(id), vec![]);
            } else {
                respond(rq, 404, "application/xml", status_xml(404, "Invalid channel"), vec![]);
            }
        }
        _ => respond(rq, 404, "application/xml", status_xml(404, "Not Found"), vec![]),
    }
}

fn tracks_xml(cfg: &IsapiConfig) -> String {
    let mut s = String::from("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<TrackList version=\"1.0\" xmlns=\"http://www.hikvision.com/ver20/XMLSchema\">\n");
    for t in &cfg.tracks {
        s.push_str(&format!(
            "<Track>\n<id>{t}</id>\n<Channel>{}</Channel>\n<Enable>true</Enable>\n<Description>trackType=standard,sourceType=MPEG4-VIDEO,codecType=H.264-BP,resolution=1280x720,framerate=25.000000 fps,bitrate=2048 kbps</Description>\n<TrackGUID>{{00000000-0000-0000-0000-00000000{t:04}}}</TrackGUID>\n<DefaultRecordingMode>CMR</DefaultRecordingMode>\n</Track>\n",
            t / 100
        ));
    }
    s.push_str("</TrackList>\n");
    s
}

pub(crate) fn tag_values(xml: &str, tag: &str) -> Vec<String> {
    let (open, close) = (format!("<{tag}>"), format!("</{tag}>"));
    let mut out = Vec::new();
    let mut rest = xml;
    while let Some(i) = rest.find(&open) {
        let after = &rest[i + open.len()..];
        let Some(j) = after.find(&close) else { break };
        out.push(after[..j].trim().to_string());
        rest = &after[j + close.len()..];
    }
    out
}

fn parse_ts(s: &str) -> Option<NaiveDateTime> {
    NaiveDateTime::parse_from_str(s, TS).ok()
}

fn search_xml(cfg: &IsapiConfig, req: &str, host: &str) -> Option<String> {
    let search_id = tag_values(req, "searchID").into_iter().next()?;
    let tracks: Vec<u32> = tag_values(req, "trackID").iter().filter_map(|t| t.parse().ok()).collect();
    let from = parse_ts(tag_values(req, "startTime").first()?)?;
    let to = parse_ts(tag_values(req, "endTime").first()?)?;
    let max: usize = tag_values(req, "maxResults").first()?.parse().ok()?;
    // Hikvision's own spelling of the element.
    let pos: usize = tag_values(req, "searchResultPostion").first()?.parse().ok()?;
    let mut matches: Vec<&Clip> = cfg
        .clips
        .iter()
        .filter(|c| (tracks.is_empty() || tracks.contains(&c.track)) && c.start < to && c.end > from)
        .collect();
    matches.sort_by_key(|c| (c.track, c.start));
    let page: Vec<&&Clip> = matches.iter().skip(pos).take(max.min(cfg.page_cap)).collect();
    let status = if matches.is_empty() {
        "NO MATCHES"
    } else if pos + page.len() < matches.len() {
        "MORE"
    } else {
        "OK"
    };
    let mut s = format!(
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<CMSearchResult version=\"1.0\" xmlns=\"http://www.hikvision.com/ver20/XMLSchema\">\n<searchID>{search_id}</searchID>\n<responseStatus>true</responseStatus>\n<responseStatusStrg>{status}</responseStatusStrg>\n<numOfMatches>{}</numOfMatches>\n<matchList>\n",
        page.len()
    );
    for c in page {
        s.push_str(&format!(
            "<searchMatchItem>\n<sourceID>{{00000000-0000-0000-0000-00000000{t:04}}}</sourceID>\n<trackID>{t}</trackID>\n<timeSpan>\n<startTime>{}</startTime>\n<endTime>{}</endTime>\n</timeSpan>\n<mediaSegmentDescriptor>\n<contentType>video</contentType>\n<codecType>H.264-BP</codecType>\n<playbackURI>{}</playbackURI>\n</mediaSegmentDescriptor>\n<metadataMatches>\n<metadataDescriptor>recordType.meta.std-cgi.com/CMR</metadataDescriptor>\n</metadataMatches>\n</searchMatchItem>\n",
            c.start.format(TS),
            c.end.format(TS),
            c.playback_uri(host).replace('&', "&amp;"),
            t = c.track
        ));
    }
    s.push_str("</matchList>\n</CMSearchResult>\n");
    Some(s)
}

fn query_param<'a>(uri: &'a str, key: &str) -> Option<&'a str> {
    let q = uri.split_once('?')?.1;
    q.split('&').find_map(|kv| kv.split_once('=').filter(|(k, _)| *k == key).map(|(_, v)| v))
}

fn download_payload(cfg: &IsapiConfig, req: &str) -> Option<Vec<u8>> {
    let uri = tag_values(req, "playbackURI").into_iter().next()?.replace("&amp;", "&");
    let track: u32 = uri.split("/Streaming/tracks/").nth(1)?.split('/').next()?.parse().ok()?;
    let name = query_param(&uri, "name")?;
    let clip = cfg.clips.iter().find(|c| c.track == track && c.name == name)?;
    Some(fake_dav(clip))
}

/// Synthetic recording: 40-byte IMKH wrapper followed by `size` payload bytes.
pub fn fake_dav(clip: &Clip) -> Vec<u8> {
    let mut v = Vec::with_capacity(IMKH_HEADER_LEN + clip.size as usize);
    v.extend_from_slice(b"IMKH");
    v.extend_from_slice(&[0x01, 0x01, 0x00, 0x00, 0x02, 0x00, 0x00, 0x00]);
    v.resize(IMKH_HEADER_LEN, 0);
    let seed = clip.name.bytes().fold(clip.track, |a, b| a.wrapping_mul(31).wrapping_add(b as u32));
    v.extend((0..clip.size).map(|i| (seed.wrapping_add(i as u32) % 251) as u8));
    v
}

/// Tiny synthetic JPEG (SOI ... EOI); not a decodable image, only shaped like one.
pub fn fake_jpeg(channel_id: u32) -> Vec<u8> {
    let mut v = vec![0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, b'J', b'F', b'I', b'F', 0x00];
    v.extend(format!("mock-channel-{channel_id}").bytes());
    v.extend_from_slice(&[0xFF, 0xD9]);
    v
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn tag_values_extracts_all() {
        let x = "<a><trackID>101</trackID><trackID>201</trackID></a>";
        assert_eq!(tag_values(x, "trackID"), vec!["101", "201"]);
    }
    #[test]
    fn fake_dav_is_size_plus_40_with_magic() {
        let cfg = IsapiConfig::eight_channel_dvr(1);
        let c = &cfg.clips[0];
        let d = fake_dav(c);
        assert_eq!(&d[..4], b"IMKH");
        assert_eq!(d.len() as u64, c.size + 40);
    }
}
