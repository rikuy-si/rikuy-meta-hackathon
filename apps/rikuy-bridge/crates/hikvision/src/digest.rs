//! Client-side HTTP Digest (RFC 7616 MD5, qop=auth; RFC 2069 fallback).
use md5::{Digest, Md5};
use rand::RngCore;

fn md5_hex(s: &str) -> String {
    let mut h = Md5::new();
    h.update(s.as_bytes());
    h.finalize().iter().map(|b| format!("{b:02x}")).collect()
}

#[derive(Debug, Clone)]
pub struct Challenge {
    pub realm: String,
    pub nonce: String,
    pub opaque: Option<String>,
    pub qop_auth: bool,
    pub stale: bool,
}

impl Challenge {
    pub fn parse(header: &str) -> Option<Challenge> {
        let rest = header.trim().strip_prefix("Digest")?.trim();
        let mut realm = None;
        let mut nonce = None;
        let mut opaque = None;
        let mut qop = None;
        let mut stale = false;
        for (k, v) in split_params(rest) {
            match k.to_ascii_lowercase().as_str() {
                "realm" => realm = Some(v),
                "nonce" => nonce = Some(v),
                "opaque" => opaque = Some(v),
                "qop" => qop = Some(v),
                "stale" => stale = v.eq_ignore_ascii_case("true"),
                _ => {}
            }
        }
        Some(Challenge {
            realm: realm?,
            nonce: nonce?,
            opaque,
            qop_auth: qop.map(|q| q.split(',').any(|x| x.trim() == "auth")).unwrap_or(false),
            stale,
        })
    }
}

fn split_params(s: &str) -> Vec<(String, String)> {
    let mut out = Vec::new();
    let mut chars = s.chars().peekable();
    loop {
        while matches!(chars.peek(), Some(' ') | Some(',')) {
            chars.next();
        }
        let mut key = String::new();
        while let Some(&c) = chars.peek() {
            if c == '=' { break; }
            key.push(c);
            chars.next();
        }
        if key.is_empty() || chars.next().is_none() { break; }
        let mut val = String::new();
        if chars.peek() == Some(&'"') {
            chars.next();
            for c in chars.by_ref() {
                if c == '"' { break; }
                val.push(c);
            }
        } else {
            while let Some(&c) = chars.peek() {
                if c == ',' { break; }
                val.push(c);
                chars.next();
            }
        }
        out.push((key.trim().to_string(), val.trim().to_string()));
    }
    out
}

/// Digest session state: one challenge, an incrementing nonce count.
#[derive(Debug)]
pub struct DigestSession {
    challenge: Challenge,
    nc: u32,
}

impl DigestSession {
    pub fn new(challenge: Challenge) -> Self {
        DigestSession { challenge, nc: 0 }
    }

    /// Build the Authorization header for one request. `uri` is the exact
    /// request-target (path and query) sent on the wire.
    pub fn authorize(&mut self, method: &str, uri: &str, user: &str, pass: &str) -> String {
        self.nc += 1;
        let c = &self.challenge;
        let ha1 = md5_hex(&format!("{user}:{}:{pass}", c.realm));
        let ha2 = md5_hex(&format!("{method}:{uri}"));
        let mut h = if c.qop_auth {
            let mut raw = [0u8; 8];
            rand::thread_rng().fill_bytes(&mut raw);
            let cnonce: String = raw.iter().map(|b| format!("{b:02x}")).collect();
            let nc = format!("{:08x}", self.nc);
            let response = md5_hex(&format!("{ha1}:{}:{nc}:{cnonce}:auth:{ha2}", c.nonce));
            format!(
                "Digest username=\"{user}\", realm=\"{}\", nonce=\"{}\", uri=\"{uri}\", qop=auth, nc={nc}, cnonce=\"{cnonce}\", response=\"{response}\", algorithm=MD5",
                c.realm, c.nonce
            )
        } else {
            let response = md5_hex(&format!("{ha1}:{}:{ha2}", c.nonce));
            format!(
                "Digest username=\"{user}\", realm=\"{}\", nonce=\"{}\", uri=\"{uri}\", response=\"{response}\", algorithm=MD5",
                c.realm, c.nonce
            )
        };
        if let Some(o) = &c.opaque {
            h.push_str(&format!(", opaque=\"{o}\""));
        }
        h
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_hikvision_style_challenge() {
        let c = Challenge::parse(
            r#"Digest qop="auth", realm="DS-7108HGHI-F1", nonce="4e5468694e7a6b354f4441364f54637a5a6d4d324d6a553d", stale="FALSE""#,
        )
        .unwrap();
        assert_eq!(c.realm, "DS-7108HGHI-F1");
        assert!(c.qop_auth);
        assert!(!c.stale);
    }

    #[test]
    fn rfc2617_reference_vector() {
        // RFC 2617 section 3.5 example, with a fixed cnonce.
        let ha1 = md5_hex("Mufasa:testrealm@host.com:Circle Of Life");
        let ha2 = md5_hex("GET:/dir/index.html");
        let r = md5_hex(&format!("{ha1}:dcd98b7102dd2f0e8b11d0f600bfb0c093:00000001:0a4f113b:auth:{ha2}"));
        assert_eq!(r, "6629fae49393a05397450978507c4ef1");
    }
}
