//! Mock object store standing in for Cloudflare R2 behind presigned PUT URLs.
//!
//! The signature scheme is a stand-in, not AWS SigV4. What matters for the
//! bridge is the behavior it has to cope with: the URL is opaque, it is bound
//! to one key, one method and one length, it expires, and the store requires
//! a Content-Length (no chunked uploads, as with S3/R2 presigned PUTs).
use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use std::thread::JoinHandle;
use std::time::{SystemTime, UNIX_EPOCH};

use sha2::{Digest, Sha256};
use tiny_http::{Request, Server};

use crate::http::{body, header, respond};

pub const BUCKET: &str = "rikuy-recordings";

#[derive(Default)]
struct StoreState {
    objects: HashMap<String, Vec<u8>>,
    puts: u32,
    rejected_expired: u32,
    rejected_other: u32,
}

/// What the backend needs to sign URLs and verify uploads.
#[derive(Clone)]
pub struct StoreHandle {
    pub base_url: String,
    secret: String,
    state: Arc<Mutex<StoreState>>,
}

fn now() -> i64 {
    SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs() as i64
}

fn hex(b: &[u8]) -> String {
    b.iter().map(|x| format!("{x:02x}")).collect()
}

fn sign(secret: &str, method: &str, path: &str, expires: i64, len: u64) -> String {
    hex(&Sha256::digest(format!("{secret}\n{method}\n{path}\n{expires}\n{len}").as_bytes()))
}

impl StoreHandle {
    /// Presigned PUT for `key`, valid for `ttl_secs` (negative = already expired).
    pub fn presign_put(&self, key: &str, len: u64, ttl_secs: i64) -> (String, i64) {
        let expires = now() + ttl_secs;
        let path = format!("/{BUCKET}/{key}");
        let sig = sign(&self.secret, "PUT", &path, expires, len);
        (
            format!("{}{path}?X-Mock-Expires={expires}&X-Mock-Length={len}&X-Mock-Signature={sig}", self.base_url),
            expires,
        )
    }

    /// HEAD: size and SHA-256 of a stored object.
    pub fn head(&self, key: &str) -> Option<(u64, String)> {
        let st = self.state.lock().unwrap();
        st.objects.get(key).map(|b| (b.len() as u64, hex(&Sha256::digest(b))))
    }

    pub fn keys(&self) -> Vec<String> {
        let mut k: Vec<String> = self.state.lock().unwrap().objects.keys().cloned().collect();
        k.sort();
        k
    }
    pub fn puts(&self) -> u32 {
        self.state.lock().unwrap().puts
    }
    pub fn rejected_expired(&self) -> u32 {
        self.state.lock().unwrap().rejected_expired
    }
    pub fn rejected_other(&self) -> u32 {
        self.state.lock().unwrap().rejected_other
    }
}

pub struct MockObjectStore {
    server: Arc<Server>,
    handle: Option<JoinHandle<()>>,
    store: StoreHandle,
}

impl MockObjectStore {
    pub fn start() -> Self {
        let server = Arc::new(Server::http("127.0.0.1:0").expect("bind mock object store"));
        let base_url = format!("http://{}", server.server_addr().to_ip().unwrap());
        let store = StoreHandle { base_url, secret: "mock-r2-signing-secret".into(), state: Default::default() };
        let (s, h) = (server.clone(), store.clone());
        let handle = std::thread::spawn(move || {
            for rq in s.incoming_requests() {
                handle_request(rq, &h);
            }
        });
        MockObjectStore { server, handle: Some(handle), store }
    }

    pub fn handle(&self) -> StoreHandle {
        self.store.clone()
    }
}

impl std::ops::Deref for MockObjectStore {
    type Target = StoreHandle;
    fn deref(&self) -> &StoreHandle {
        &self.store
    }
}

impl Drop for MockObjectStore {
    fn drop(&mut self) {
        self.server.unblock();
        if let Some(h) = self.handle.take() {
            let _ = h.join();
        }
    }
}

fn s3_error(rq: Request, status: u16, code: &str, msg: &str) {
    let xml = format!("<?xml version=\"1.0\" encoding=\"UTF-8\"?><Error><Code>{code}</Code><Message>{msg}</Message></Error>");
    respond(rq, status, "application/xml", xml.into_bytes(), vec![]);
}

fn handle_request(mut rq: Request, store: &StoreHandle) {
    let url = rq.url().to_string();
    let (path, query) = url.split_once('?').unwrap_or((url.as_str(), ""));
    let path = path.to_string();
    let q = |k: &str| query.split('&').find_map(|kv| kv.split_once('=').filter(|(a, _)| *a == k).map(|(_, v)| v.to_string()));
    let method = rq.method().as_str().to_string();
    let reject = |st: &StoreHandle, expired: bool| {
        let mut s = st.state.lock().unwrap();
        if expired { s.rejected_expired += 1 } else { s.rejected_other += 1 }
    };

    let (Some(expires), Some(len), Some(sig)) = (
        q("X-Mock-Expires").and_then(|v| v.parse::<i64>().ok()),
        q("X-Mock-Length").and_then(|v| v.parse::<u64>().ok()),
        q("X-Mock-Signature"),
    ) else {
        reject(store, false);
        return s3_error(rq, 403, "AccessDenied", "missing signature");
    };
    if sig != sign(&store.secret, &method, &path, expires, len) {
        reject(store, false);
        return s3_error(rq, 403, "SignatureDoesNotMatch", "signature does not match");
    }
    if now() > expires {
        reject(store, true);
        return s3_error(rq, 403, "AccessDenied", "Request has expired");
    }
    if header(&rq, "Content-Length").and_then(|v| v.parse::<u64>().ok()) != Some(len) {
        reject(store, false);
        return s3_error(rq, 411, "MissingContentLength", "Content-Length must match the signed length");
    }
    let data = body(&mut rq);
    if data.len() as u64 != len {
        reject(store, false);
        return s3_error(rq, 400, "IncompleteBody", "body shorter than Content-Length");
    }
    let key = path.trim_start_matches(&format!("/{BUCKET}/")).to_string();
    {
        let mut s = store.state.lock().unwrap();
        s.puts += 1;
        s.objects.insert(key, data);
    }
    respond(rq, 200, "application/xml", vec![], vec![]);
}
