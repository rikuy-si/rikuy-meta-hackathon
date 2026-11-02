//! Mock Rikuy backend: job queue, report sink, snapshot sink, and presigned
//! upload grants for recordings (when started with an object store).
use std::collections::{HashMap, VecDeque};
use std::sync::{Arc, Mutex};
use std::thread::JoinHandle;

use serde_json::{json, Value};
use tiny_http::{Request, Server};

use crate::http::{body, header, respond};
use crate::objstore::StoreHandle;

#[derive(Default)]
struct State {
    token: String,
    queue: VecDeque<Value>,
    reports: Vec<Value>,
    artifacts: HashMap<(String, String), Vec<u8>>,
    polls: u32,
    unauthorized: u32,
    // object storage
    store: Option<StoreHandle>,
    url_ttl: i64,
    expire_next_grants: u32,
    grant_base_override: Option<String>,
    upload_requests: u32,
    grants_issued: u32,
    verified: u32,
}

pub struct MockBackend {
    server: Arc<Server>,
    state: Arc<Mutex<State>>,
    handle: Option<JoinHandle<()>>,
    pub base_url: String,
}

impl MockBackend {
    pub fn start(token: &str) -> Self {
        Self::start_on("127.0.0.1:0", token)
    }

    /// A backend that hands out presigned PUT URLs into `store`.
    pub fn start_with_store(token: &str, store: StoreHandle) -> Self {
        let b = Self::start(token);
        {
            let mut st = b.state.lock().unwrap();
            st.store = Some(store);
        }
        b
    }

    pub fn start_on(addr: &str, token: &str) -> Self {
        let server = Arc::new(Server::http(addr).expect("bind mock backend"));
        let base_url = format!("http://{}", server.server_addr().to_ip().unwrap());
        let state = Arc::new(Mutex::new(State { token: token.into(), url_ttl: 900, ..Default::default() }));
        let (s, st) = (server.clone(), state.clone());
        let handle = std::thread::spawn(move || {
            for rq in s.incoming_requests() {
                handle_request(rq, &st);
            }
        });
        MockBackend { server, state, handle: Some(handle), base_url }
    }

    /// The next `n` grants are issued already expired.
    pub fn expire_next_grants(&self, n: u32) {
        self.state.lock().unwrap().expire_next_grants = n;
    }
    /// Point grants at another base URL (e.g. a dead object store).
    pub fn override_grant_base(&self, base: &str) {
        self.state.lock().unwrap().grant_base_override = Some(base.into());
    }

    pub fn enqueue(&self, job: Value) {
        self.state.lock().unwrap().queue.push_back(job);
    }
    pub fn reports(&self) -> Vec<Value> {
        self.state.lock().unwrap().reports.clone()
    }
    pub fn report_for(&self, job_id: &str) -> Option<Value> {
        self.reports().into_iter().rev().find(|r| r["job_id"] == job_id)
    }
    pub fn artifact(&self, job_id: &str, name: &str) -> Option<Vec<u8>> {
        self.state.lock().unwrap().artifacts.get(&(job_id.into(), name.into())).cloned()
    }
    pub fn polls(&self) -> u32 {
        self.state.lock().unwrap().polls
    }
    pub fn unauthorized(&self) -> u32 {
        self.state.lock().unwrap().unauthorized
    }
    pub fn upload_requests(&self) -> u32 {
        self.state.lock().unwrap().upload_requests
    }
    pub fn grants_issued(&self) -> u32 {
        self.state.lock().unwrap().grants_issued
    }
    pub fn verified(&self) -> u32 {
        self.state.lock().unwrap().verified
    }
}

impl Drop for MockBackend {
    fn drop(&mut self) {
        self.server.unblock();
        if let Some(h) = self.handle.take() {
            let _ = h.join();
        }
    }
}

/// Object key layout chosen by the backend, never by the bridge.
pub fn object_key(bridge: &str, job_id: &str, name: &str) -> String {
    format!("recordings/{bridge}/{job_id}/{name}")
}

fn handle_request(mut rq: Request, state: &Arc<Mutex<State>>) {
    let mut st = state.lock().unwrap();
    let expected = format!("Bearer {}", st.token);
    if header(&rq, "Authorization").as_deref() != Some(expected.as_str()) {
        st.unauthorized += 1;
        return respond(rq, 401, "application/json", br#"{"error":"unauthorized"}"#.to_vec(), vec![]);
    }
    let method = rq.method().as_str().to_string();
    let path = rq.url().split('?').next().unwrap_or("").to_string();
    let parts: Vec<&str> = path.trim_matches('/').split('/').collect();
    match (method.as_str(), parts.as_slice()) {
        ("GET", ["v1", "bridge", "jobs", "next"]) => {
            st.polls += 1;
            match st.queue.pop_front() {
                Some(job) => respond(rq, 200, "application/json", serde_json::to_vec(&job).unwrap(), vec![]),
                None => respond(rq, 204, "application/json", vec![], vec![]),
            }
        }
        ("POST", ["v1", "bridge", "jobs", id, "uploads"]) => {
            let id = id.to_string();
            let Some(store) = st.store.clone() else {
                return respond(rq, 404, "application/json", br#"{"error":"object storage not configured"}"#.to_vec(), vec![]);
            };
            st.upload_requests += 1;
            let req: Value = match serde_json::from_slice(&body(&mut rq)) {
                Ok(v) => v,
                Err(_) => return respond(rq, 400, "application/json", br#"{"error":"bad json"}"#.to_vec(), vec![]),
            };
            let bridge = req["bridge"].as_str().unwrap_or("unknown").to_string();
            let (mut grants, mut stored) = (vec![], vec![]);
            for a in req["artifacts"].as_array().cloned().unwrap_or_default() {
                let name = a["name"].as_str().unwrap_or_default().to_string();
                let bytes = a["bytes"].as_u64().unwrap_or(0);
                let sha = a["sha256"].as_str().unwrap_or_default().to_string();
                let ct = a["content_type"].as_str().unwrap_or("application/octet-stream").to_string();
                let key = object_key(&bridge, &id, &name);
                if store.head(&key) == Some((bytes, sha)) {
                    stored.push(json!({ "name": name, "key": key }));
                    continue;
                }
                let ttl = if st.expire_next_grants > 0 {
                    st.expire_next_grants -= 1;
                    -60
                } else {
                    st.url_ttl
                };
                let (mut url, expires) = store.presign_put(&key, bytes, ttl);
                if let Some(base) = &st.grant_base_override {
                    url = url.replacen(&store.base_url, base, 1);
                }
                st.grants_issued += 1;
                grants.push(json!({
                    "name": name, "key": key, "method": "PUT", "url": url,
                    "headers": { "Content-Type": ct }, "expires_at": expires,
                }));
            }
            let resp = json!({ "grants": grants, "stored": stored });
            respond(rq, 200, "application/json", serde_json::to_vec(&resp).unwrap(), vec![]);
        }
        ("POST", ["v1", "bridge", "jobs", _id, "report"]) => {
            let b = body(&mut rq);
            let v: Value = match serde_json::from_slice(&b) {
                Ok(v) => v,
                Err(_) => return respond(rq, 400, "application/json", br#"{"error":"bad json"}"#.to_vec(), vec![]),
            };
            // Verify each uploaded object (HEAD) before telling the bridge it may delete.
            let mut delete = vec![];
            if let Some(store) = &st.store {
                for a in v["artifacts"].as_array().cloned().unwrap_or_default() {
                    if a["uploaded"] != true {
                        continue;
                    }
                    let Some(key) = a["object_key"].as_str() else { continue };
                    let want = (a["bytes"].as_u64().unwrap_or(0), a["sha256"].as_str().unwrap_or_default().to_string());
                    if store.head(key) == Some(want) {
                        delete.push(a["name"].clone());
                    }
                }
            }
            st.verified += delete.len() as u32;
            st.reports.push(v);
            if delete.is_empty() {
                respond(rq, 204, "application/json", vec![], vec![]);
            } else {
                respond(rq, 200, "application/json", serde_json::to_vec(&json!({ "delete": delete })).unwrap(), vec![]);
            }
        }
        ("PUT", ["v1", "bridge", "jobs", id, "artifacts", name]) => {
            let key = (id.to_string(), name.to_string());
            let b = body(&mut rq);
            st.artifacts.insert(key, b);
            respond(rq, 204, "application/json", vec![], vec![]);
        }
        _ => respond(rq, 404, "application/json", br#"{"error":"not found"}"#.to_vec(), vec![]),
    }
}
