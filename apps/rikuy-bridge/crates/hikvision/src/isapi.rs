//! Hikvision ISAPI client: Digest auth, liveness, discovery and paged search.
use std::io::Read;
use std::time::Duration;

use chrono::NaiveDateTime;
use rand::RngCore;
use rikuy_bridge_common::liveness::{probe, DEFAULT_PROBE_TIMEOUT};
use rikuy_bridge_common::{BridgeError, Credential};
use url::Url;

use crate::digest::{Challenge, DigestSession};
use crate::xml::{self, ResponseStatus, SearchResult, TrackList};

/// The DVR caps each search page at 64 results whatever `maxResults` says.
pub const PAGE_SIZE: usize = 64;
const MAX_PAGES: usize = 10_000;

#[derive(Debug, Clone, serde::Serialize)]
pub struct Track {
    pub id: u32,
    pub channel: u32,
    pub enabled: bool,
    pub description: Option<String>,
}

#[derive(Debug, Clone, serde::Serialize)]
pub struct Recording {
    pub track: u32,
    /// Local wall-clock time on the DVR.
    pub start: NaiveDateTime,
    pub end: NaiveDateTime,
    pub playback_uri: String,
    pub name: Option<String>,
    /// Payload size the DVR advertises in the playback URI (`size=`).
    pub size: Option<u64>,
}

pub struct IsapiClient {
    base: Url,
    host: String,
    port: u16,
    agent: ureq::Agent,
    credential: Credential,
    session: Option<DigestSession>,
    /// Once the device rejects the credential, never send it again.
    rejected: Option<u16>,
    probe_timeout: Duration,
}

impl IsapiClient {
    pub fn new(base_url: &str, credential: Credential) -> Result<Self, BridgeError> {
        let base = Url::parse(base_url).map_err(|e| BridgeError::Usage(format!("bad device url {base_url}: {e}")))?;
        if base.scheme() != "http" {
            return Err(BridgeError::Usage(format!("unsupported scheme {}; ISAPI on the LAN is plain http", base.scheme())));
        }
        let host = base.host_str().ok_or_else(|| BridgeError::Usage("device url has no host".into()))?.to_string();
        let port = base.port_or_known_default().unwrap_or(80);
        let agent = ureq::AgentBuilder::new()
            .timeout_connect(Duration::from_secs(5))
            .timeout_read(Duration::from_secs(60))
            .redirects(0)
            .build();
        Ok(IsapiClient { base, host, port, agent, credential, session: None, rejected: None, probe_timeout: DEFAULT_PROBE_TIMEOUT })
    }

    pub fn with_probe_timeout(mut self, t: Duration) -> Self {
        self.probe_timeout = t;
        self
    }

    pub fn host(&self) -> &str {
        &self.host
    }

    /// One ISAPI request with Digest auth. Policy:
    /// - probe the route first; a dead route is `Unreachable` with no request sent;
    /// - an unauthenticated 401 (or `stale=true`) gets exactly one credentialed retry;
    /// - a 401 to a credentialed request, or any 403, is `AuthRejected` and poisons
    ///   the client so the credential is never sent again (account lockout).
    pub fn request(&mut self, method: &str, path: &str, body: Option<&[u8]>) -> Result<ureq::Response, BridgeError> {
        if let Some(status) = self.rejected {
            return Err(BridgeError::AuthRejected { status });
        }
        probe(&self.host, self.port, self.probe_timeout)?;
        let url = self.base.join(path).map_err(|e| BridgeError::Usage(e.to_string()))?;
        let uri = match url.query() {
            Some(q) => format!("{}?{q}", url.path()),
            None => url.path().to_string(),
        };

        let mut credentialed_attempts = 0;
        loop {
            let auth = self.session.as_mut().map(|s| {
                s.authorize(method, &uri, &self.credential.username, self.credential.password.expose())
            });
            let sent_auth = auth.is_some();
            if sent_auth {
                credentialed_attempts += 1;
            }
            let mut rq = self.agent.request_url(method, &url);
            if let Some(a) = &auth {
                rq = rq.set("Authorization", a);
            }
            let result = match body {
                Some(b) => rq.set("Content-Type", "application/xml; charset=UTF-8").send_bytes(b),
                None => rq.call(),
            };
            match result {
                Ok(resp) => return Ok(resp),
                Err(ureq::Error::Status(401, resp)) => {
                    let challenge = resp.header("WWW-Authenticate").and_then(Challenge::parse);
                    let stale = challenge.as_ref().map(|c| c.stale).unwrap_or(false);
                    if (sent_auth && !stale) || credentialed_attempts >= 2 || challenge.is_none() {
                        self.rejected = Some(401);
                        self.session = None;
                        return Err(BridgeError::AuthRejected { status: 401 });
                    }
                    self.session = Some(DigestSession::new(challenge.unwrap()));
                }
                Err(ureq::Error::Status(403, _)) => {
                    self.rejected = Some(403);
                    self.session = None;
                    return Err(BridgeError::AuthRejected { status: 403 });
                }
                Err(ureq::Error::Status(code, resp)) => {
                    let detail = resp
                        .into_string()
                        .ok()
                        .and_then(|s| quick_xml::de::from_str::<ResponseStatus>(&s).ok())
                        .and_then(|r| r.string)
                        .unwrap_or_default();
                    return Err(BridgeError::Protocol(format!("{method} {path}: HTTP {code} {detail}").trim().to_string()));
                }
                Err(ureq::Error::Transport(t)) => {
                    return Err(BridgeError::Unreachable(format!("{method} {path}: {t}")));
                }
            }
        }
    }

    fn request_xml(&mut self, method: &str, path: &str, body: Option<&[u8]>) -> Result<String, BridgeError> {
        let resp = self.request(method, path, body)?;
        let mut s = String::new();
        resp.into_reader()
            .take(16 * 1024 * 1024)
            .read_to_string(&mut s)
            .map_err(|e| BridgeError::Unreachable(format!("{method} {path}: read: {e}")))?;
        Ok(s)
    }

    /// `GET /ISAPI/ContentMgmt/record/tracks`
    pub fn tracks(&mut self) -> Result<Vec<Track>, BridgeError> {
        let s = self.request_xml("GET", "/ISAPI/ContentMgmt/record/tracks", None)?;
        let list: TrackList = quick_xml::de::from_str(&s).map_err(|e| BridgeError::Protocol(format!("tracks xml: {e}")))?;
        Ok(list
            .tracks
            .into_iter()
            .map(|t| Track {
                id: t.id,
                channel: t.channel.unwrap_or(t.id / 100),
                enabled: t.enable.unwrap_or(true),
                description: t.description,
            })
            .collect())
    }

    /// Paged `POST /ISAPI/ContentMgmt/search` until the range is covered.
    pub fn search(&mut self, from: NaiveDateTime, to: NaiveDateTime, tracks: &[u32]) -> Result<Vec<Recording>, BridgeError> {
        let tracks: Vec<u32> = if tracks.is_empty() {
            self.tracks()?.into_iter().filter(|t| t.enabled).map(|t| t.id).collect()
        } else {
            tracks.to_vec()
        };
        let search_id = new_search_id();
        let mut out = Vec::new();
        for _ in 0..MAX_PAGES {
            let body = xml::search_request(&search_id, &tracks, from, to, PAGE_SIZE, out.len());
            let s = self.request_xml("POST", "/ISAPI/ContentMgmt/search", Some(body.as_bytes()))?;
            let page: SearchResult =
                quick_xml::de::from_str(&s).map_err(|e| BridgeError::Protocol(format!("search xml: {e}")))?;
            let items = page.match_list.unwrap_or_default().items;
            let got = items.len();
            for it in items {
                out.push(recording_from(it)?);
            }
            match page.status.as_str() {
                "MORE" if got > 0 => continue,
                "MORE" => return Err(BridgeError::Protocol("search: MORE with an empty page".into())),
                "OK" | "NO MATCHES" => return Ok(out),
                other => return Err(BridgeError::Protocol(format!("search: unexpected status {other}"))),
            }
        }
        Err(BridgeError::Protocol("search: page limit exceeded".into()))
    }
}

fn recording_from(it: xml::MatchItem) -> Result<Recording, BridgeError> {
    let bad = |what: &str| BridgeError::Protocol(format!("search item: bad {what}"));
    let uri = it.media.playback_uri;
    let param = |k: &str| {
        uri.split_once('?').and_then(|(_, q)| q.split('&').find_map(|kv| kv.split_once('=').filter(|(a, _)| *a == k).map(|(_, v)| v.to_string())))
    };
    Ok(Recording {
        track: it.track,
        start: xml::parse_ts(&it.span.start).ok_or_else(|| bad("startTime"))?,
        end: xml::parse_ts(&it.span.end).ok_or_else(|| bad("endTime"))?,
        name: param("name"),
        size: param("size").and_then(|s| s.parse().ok()),
        playback_uri: uri,
    })
}

fn new_search_id() -> String {
    let mut b = [0u8; 16];
    rand::thread_rng().fill_bytes(&mut b);
    b[6] = (b[6] & 0x0f) | 0x40;
    b[8] = (b[8] & 0x3f) | 0x80;
    let h: String = b.iter().map(|x| format!("{x:02x}")).collect();
    format!("{}-{}-{}-{}-{}", &h[0..8], &h[8..12], &h[12..16], &h[16..20], &h[20..32])
}
