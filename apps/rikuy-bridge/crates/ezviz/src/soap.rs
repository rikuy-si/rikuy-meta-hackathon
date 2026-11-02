//! ONVIF SOAP transport: WS-Security UsernameToken, clock skew, auth policy.
//!
//! Policy (same as the Hikvision connector):
//! - probe the route before every request; a dead route sends nothing;
//! - a credentialed request the device rejects (HTTP 401/403, or a SOAP
//!   `NotAuthorized` fault) poisons the client: the credential is never sent
//!   again, because cameras lock accounts after repeated failures;
//! - the only retry is the one an HTTP Digest challenge asks for, once.
use std::io::Read;
use std::time::Duration;

use base64::Engine;
use chrono::{NaiveDateTime, Utc};
use rand::RngCore;
use rikuy_bridge_common::digest::{Challenge, DigestSession};
use rikuy_bridge_common::liveness::{probe, DEFAULT_PROBE_TIMEOUT};
use rikuy_bridge_common::{BridgeError, Credential};
use sha1::{Digest, Sha1};
use url::Url;

use crate::xml::{self, escape, Element};

pub const MAX_RESPONSE: u64 = 16 * 1024 * 1024;
const B64: base64::engine::GeneralPurpose = base64::engine::general_purpose::STANDARD;

pub struct SoapClient {
    /// `http://host:port` the bridge reaches the device at.
    pub(crate) origin: Url,
    host: String,
    port: u16,
    agent: ureq::Agent,
    pub(crate) credential: Credential,
    rejected: Option<u16>,
    http_digest: Option<DigestSession>,
    /// device UTC - host UTC, applied to WS-Security `Created`.
    pub skew_secs: i64,
    probe_timeout: Duration,
}

/// WS-Security PasswordDigest = Base64(SHA1(nonce + created + password)).
pub fn password_digest(nonce: &[u8], created: &str, password: &str) -> String {
    let mut h = Sha1::new();
    h.update(nonce);
    h.update(created.as_bytes());
    h.update(password.as_bytes());
    B64.encode(h.finalize())
}

impl SoapClient {
    pub fn new(base_url: &str, credential: Credential) -> Result<Self, BridgeError> {
        let url = Url::parse(base_url).map_err(|e| BridgeError::Usage(format!("bad device url {base_url}: {e}")))?;
        if url.scheme() != "http" {
            return Err(BridgeError::Usage(format!("unsupported scheme {}; ONVIF on the LAN is plain http", url.scheme())));
        }
        let host = url.host_str().ok_or_else(|| BridgeError::Usage("device url has no host".into()))?.to_string();
        let port = url.port_or_known_default().unwrap_or(80);
        let origin = Url::parse(&format!("http://{}:{port}/", fmt_host(&host))).map_err(|e| BridgeError::Usage(e.to_string()))?;
        let agent = ureq::AgentBuilder::new()
            .timeout_connect(Duration::from_secs(5))
            .timeout_read(Duration::from_secs(30))
            .redirects(0)
            .build();
        Ok(SoapClient {
            origin,
            host,
            port,
            agent,
            credential,
            rejected: None,
            http_digest: None,
            skew_secs: 0,
            probe_timeout: DEFAULT_PROBE_TIMEOUT,
        })
    }

    pub fn host(&self) -> &str {
        &self.host
    }

    pub fn route(&self) -> (String, u16) {
        (self.host.clone(), self.port)
    }

    pub fn rejected(&self) -> Option<u16> {
        self.rejected
    }

    pub fn poison(&mut self, status: u16) -> BridgeError {
        self.rejected = Some(status);
        self.http_digest = None;
        BridgeError::AuthRejected { status }
    }

    /// Point a device-reported HTTP address at the host/port the bridge
    /// actually reaches. Cameras report their own LAN IP in XAddrs and media
    /// URIs; behind NAT, a VPN or a port forward that address is wrong.
    pub fn rebase_http(&self, reported: &str) -> Result<Url, BridgeError> {
        let mut u = Url::parse(reported)
            .or_else(|_| self.origin.join(reported))
            .map_err(|e| BridgeError::Protocol(format!("bad device address {reported}: {e}")))?;
        u.set_host(Some(&self.host)).map_err(|e| BridgeError::Protocol(e.to_string()))?;
        u.set_port(Some(self.port)).map_err(|_| BridgeError::Protocol("cannot set port".into()))?;
        Ok(u)
    }

    fn envelope(&self, body: &str, authenticated: bool) -> String {
        let header = if authenticated {
            let mut nonce = [0u8; 16];
            rand::thread_rng().fill_bytes(&mut nonce);
            let created = (Utc::now().naive_utc() + chrono::Duration::seconds(self.skew_secs))
                .format("%Y-%m-%dT%H:%M:%S%.3fZ")
                .to_string();
            let digest = password_digest(&nonce, &created, self.credential.password.expose());
            format!(
                concat!(
                    r#"<s:Header><wsse:Security s:mustUnderstand="1" "#,
                    r#"xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd" "#,
                    r#"xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">"#,
                    r#"<wsse:UsernameToken><wsse:Username>{}</wsse:Username>"#,
                    r#"<wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">{}</wsse:Password>"#,
                    r#"<wsse:Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">{}</wsse:Nonce>"#,
                    r#"<wsu:Created>{}</wsu:Created></wsse:UsernameToken></wsse:Security></s:Header>"#
                ),
                escape(&self.credential.username),
                digest,
                B64.encode(nonce),
                created
            )
        } else {
            String::new()
        };
        format!(
            concat!(
                r#"<?xml version="1.0" encoding="UTF-8"?>"#,
                r#"<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" "#,
                r#"xmlns:tt="http://www.onvif.org/ver10/schema" "#,
                r#"xmlns:tds="http://www.onvif.org/ver10/device/wsdl" "#,
                r#"xmlns:tr2="http://www.onvif.org/ver20/media/wsdl" "#,
                r#"xmlns:tse="http://www.onvif.org/ver10/search/wsdl" "#,
                r#"xmlns:trp="http://www.onvif.org/ver10/replay/wsdl">"#,
                "{}<s:Body>{}</s:Body></s:Envelope>"
            ),
            header, body
        )
    }

    /// Call one operation. Returns the first element inside the SOAP Body.
    pub fn call(&mut self, xaddr: &Url, body: &str, authenticated: bool) -> Result<Element, BridgeError> {
        if let Some(status) = self.rejected {
            return Err(BridgeError::AuthRejected { status });
        }
        probe(&self.host, self.port, self.probe_timeout)?;
        let op = body.trim_start_matches('<').split([' ', '>', '/']).next().unwrap_or("?").to_string();
        let uri = match xaddr.query() {
            Some(q) => format!("{}?{q}", xaddr.path()),
            None => xaddr.path().to_string(),
        };
        let mut digest_retried = false;
        loop {
            let envelope = self.envelope(body, authenticated);
            let mut rq = self.agent.request_url("POST", xaddr).set("Content-Type", "application/soap+xml; charset=utf-8");
            if authenticated {
                if let Some(s) = self.http_digest.as_mut() {
                    let a = s.authorize("POST", &uri, &self.credential.username, self.credential.password.expose());
                    rq = rq.set("Authorization", &a);
                }
            }
            match rq.send_string(&envelope) {
                Ok(resp) => return parse_body(resp, &op),
                Err(ureq::Error::Status(401, resp)) => {
                    let challenge = resp.header("WWW-Authenticate").and_then(Challenge::parse);
                    match challenge {
                        // Some cameras want HTTP Digest on top of (or instead of)
                        // WS-Security: one credentialed retry, never more.
                        Some(c) if authenticated && !digest_retried && (self.http_digest.is_none() || c.stale) => {
                            self.http_digest = Some(DigestSession::new(c));
                            digest_retried = true;
                        }
                        _ if !authenticated => {
                            return Err(BridgeError::Protocol(format!("{op}: device requires authentication")));
                        }
                        _ => return Err(self.poison(401)),
                    }
                }
                Err(ureq::Error::Status(403, _)) if authenticated => return Err(self.poison(403)),
                Err(ureq::Error::Status(code, resp)) => {
                    let text = read_limited(resp).unwrap_or_default();
                    let fault = Fault::from_xml(&text);
                    if let Some(f) = &fault {
                        if f.is_auth() {
                            if authenticated {
                                return Err(self.poison(401));
                            }
                            return Err(BridgeError::Protocol(format!("{op}: device requires authentication")));
                        }
                        if f.is_not_supported() {
                            return Err(BridgeError::Unsupported(format!("{op}: {}", f.describe())));
                        }
                    }
                    let detail = fault.map(|f| f.describe()).unwrap_or_default();
                    return Err(BridgeError::Protocol(format!("{op}: HTTP {code} {detail}").trim().to_string()));
                }
                Err(ureq::Error::Transport(t)) => return Err(BridgeError::Unreachable(format!("{op}: {t}"))),
            }
        }
    }

    /// GET a device URL (snapshot) with HTTP Digest/Basic-free auth policy.
    pub fn get_bytes(&mut self, url: &Url, max: u64) -> Result<(Vec<u8>, Option<String>), BridgeError> {
        if let Some(status) = self.rejected {
            return Err(BridgeError::AuthRejected { status });
        }
        probe(&self.host, self.port, self.probe_timeout)?;
        let uri = match url.query() {
            Some(q) => format!("{}?{q}", url.path()),
            None => url.path().to_string(),
        };
        let mut session: Option<DigestSession> = None;
        let mut attempts = 0;
        loop {
            let mut rq = self.agent.request_url("GET", url);
            if let Some(s) = session.as_mut() {
                attempts += 1;
                rq = rq.set("Authorization", &s.authorize("GET", &uri, &self.credential.username, self.credential.password.expose()));
            }
            match rq.call() {
                Ok(resp) => {
                    let ct = resp.header("Content-Type").map(|s| s.to_string());
                    let mut buf = Vec::new();
                    resp.into_reader()
                        .take(max)
                        .read_to_end(&mut buf)
                        .map_err(|e| BridgeError::Unreachable(format!("GET {}: read: {e}", url.path())))?;
                    return Ok((buf, ct));
                }
                Err(ureq::Error::Status(401, resp)) => {
                    let c = resp.header("WWW-Authenticate").and_then(Challenge::parse);
                    match c {
                        Some(c) if attempts == 0 || (c.stale && attempts < 2) => session = Some(DigestSession::new(c)),
                        _ => return Err(self.poison(401)),
                    }
                }
                Err(ureq::Error::Status(403, _)) => return Err(self.poison(403)),
                Err(ureq::Error::Status(code, _)) => {
                    return Err(BridgeError::Protocol(format!("GET {}: HTTP {code}", url.path())))
                }
                Err(ureq::Error::Transport(t)) => return Err(BridgeError::Unreachable(format!("GET {}: {t}", url.path()))),
            }
        }
    }
}

fn fmt_host(h: &str) -> String {
    if h.contains(':') && !h.starts_with('[') {
        format!("[{h}]")
    } else {
        h.to_string()
    }
}

fn read_limited(resp: ureq::Response) -> Result<String, BridgeError> {
    let mut s = String::new();
    resp.into_reader()
        .take(MAX_RESPONSE)
        .read_to_string(&mut s)
        .map_err(|e| BridgeError::Unreachable(format!("read: {e}")))?;
    Ok(s)
}

fn parse_body(resp: ureq::Response, op: &str) -> Result<Element, BridgeError> {
    let text = read_limited(resp)?;
    let env = xml::parse(&text).map_err(|e| BridgeError::Protocol(format!("{op}: {e}")))?;
    let body = env.child("Body").ok_or_else(|| BridgeError::Protocol(format!("{op}: no SOAP Body")))?;
    if let Some(f) = body.child("Fault") {
        let f = Fault::from_element(f);
        return Err(BridgeError::Protocol(format!("{op}: {}", f.describe())));
    }
    body.children.first().cloned().ok_or_else(|| BridgeError::Protocol(format!("{op}: empty SOAP Body")))
}

#[derive(Debug)]
struct Fault {
    codes: Vec<String>,
    reason: String,
}

impl Fault {
    fn from_xml(s: &str) -> Option<Fault> {
        let env = xml::parse(s).ok()?;
        env.find("Fault").map(Fault::from_element)
    }
    fn from_element(f: &Element) -> Fault {
        let mut vals = Vec::new();
        f.find_all("Value", &mut vals);
        let mut codes: Vec<String> = vals.iter().map(|v| v.trimmed().to_string()).collect();
        if let Some(c) = f.text_of("faultcode") {
            codes.push(c.to_string());
        }
        let reason = f.text_of("Text").or_else(|| f.text_of("faultstring")).unwrap_or("").to_string();
        Fault { codes, reason }
    }
    fn has(&self, needle: &str) -> bool {
        self.codes.iter().any(|c| c.rsplit(':').next() == Some(needle))
    }
    fn is_auth(&self) -> bool {
        self.has("NotAuthorized") || self.has("FailedAuthentication") || self.has("InvalidSecurity")
    }
    fn is_not_supported(&self) -> bool {
        self.has("ActionNotSupported") || self.has("NotSupported")
    }
    fn describe(&self) -> String {
        format!("fault {} {}", self.codes.join("/"), self.reason).trim().to_string()
    }
}

/// `xs:dateTime` (UTC) as used throughout ONVIF.
pub fn parse_xs_datetime(s: &str) -> Option<NaiveDateTime> {
    let s = s.trim();
    if let Ok(d) = chrono::DateTime::parse_from_rfc3339(s) {
        return Some(d.naive_utc());
    }
    // Some devices omit the zone: treat it as UTC, as the spec requires.
    NaiveDateTime::parse_from_str(s, "%Y-%m-%dT%H:%M:%S%.f").ok()
}

pub fn fmt_xs_datetime(t: NaiveDateTime) -> String {
    t.format("%Y-%m-%dT%H:%M:%SZ").to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn password_digest_matches_reference() {
        // python3 -c 'import hashlib,base64;print(base64.b64encode(hashlib.sha1(
        //   bytes(range(16))+b"2026-11-02T15:00:00.000Z"+b"pa55").digest()).decode())'
        let d = password_digest(&(0u8..16).collect::<Vec<_>>(), "2026-11-02T15:00:00.000Z", "pa55");
        assert_eq!(d, include_str!("../tests/fixtures/wsse-digest.txt").trim());
    }

    #[test]
    fn faults_are_classified() {
        let x = r#"<s:Envelope xmlns:s="x" xmlns:ter="y"><s:Body><s:Fault><s:Code><s:Value>s:Sender</s:Value>
            <s:Subcode><s:Value>ter:NotAuthorized</s:Value></s:Subcode></s:Code>
            <s:Reason><s:Text xml:lang="en">Sender not authorized</s:Text></s:Reason></s:Fault></s:Body></s:Envelope>"#;
        let f = Fault::from_xml(x).unwrap();
        assert!(f.is_auth());
        assert!(f.describe().contains("not authorized"));
    }

    #[test]
    fn datetimes() {
        let t = parse_xs_datetime("2026-10-30T14:09:24.500Z").unwrap();
        assert_eq!(fmt_xs_datetime(t), "2026-10-30T14:09:24Z");
        assert_eq!(parse_xs_datetime("2026-10-30T09:09:24-05:00"), parse_xs_datetime("2026-10-30T14:09:24Z"));
        assert!(parse_xs_datetime("2026-10-30T14:09:24").is_some());
    }
}
