//! Server-side HTTP Digest (RFC 7616, MD5, qop=auth) verification.
use md5::{Digest, Md5};
use std::collections::HashMap;

pub fn md5_hex(s: &str) -> String {
    let mut h = Md5::new();
    h.update(s.as_bytes());
    h.finalize().iter().map(|b| format!("{b:02x}")).collect()
}

/// Parse `Digest k="v", k2=v2` into a map.
pub fn parse_params(header: &str) -> Option<HashMap<String, String>> {
    let rest = header.trim().strip_prefix("Digest")?.trim();
    let mut out = HashMap::new();
    let mut chars = rest.chars().peekable();
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
        if key.is_empty() { break; }
        chars.next(); // '='
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
        out.insert(key.trim().to_lowercase(), val.trim().to_string());
    }
    Some(out)
}

pub enum Verdict {
    Ok,
    Stale,
    Bad,
}

pub fn verify(
    header: &str,
    method: &str,
    request_uri: &str,
    user: &str,
    pass: &str,
    realm: &str,
    current_nonce: &str,
) -> Verdict {
    let Some(p) = parse_params(header) else { return Verdict::Bad };
    let get = |k: &str| p.get(k).cloned().unwrap_or_default();
    if get("username") != user || get("realm") != realm || get("uri") != request_uri {
        return Verdict::Bad;
    }
    let ha1 = md5_hex(&format!("{user}:{realm}:{pass}"));
    let ha2 = md5_hex(&format!("{method}:{request_uri}"));
    let expected = md5_hex(&format!(
        "{ha1}:{}:{}:{}:{}:{ha2}",
        get("nonce"),
        get("nc"),
        get("cnonce"),
        get("qop")
    ));
    if get("qop") != "auth" || expected != get("response") {
        return Verdict::Bad;
    }
    if get("nonce") != current_nonce {
        // Correct password, old nonce: ask the client to re-challenge.
        return Verdict::Stale;
    }
    Verdict::Ok
}
