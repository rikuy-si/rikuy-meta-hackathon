//! Mock Rikuy backend: job queue, report sink and artifact sink.
use std::collections::{HashMap, VecDeque};
use std::sync::{Arc, Mutex};
use std::thread::JoinHandle;

use serde_json::Value;
use tiny_http::{Request, Server};

use crate::http::{body, header, respond};

#[derive(Default)]
struct State {
    token: String,
    queue: VecDeque<Value>,
    reports: Vec<Value>,
    artifacts: HashMap<(String, String), Vec<u8>>,
    polls: u32,
    unauthorized: u32,
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

    pub fn start_on(addr: &str, token: &str) -> Self {
        let server = Arc::new(Server::http(addr).expect("bind mock backend"));
        let base_url = format!("http://{}", server.server_addr().to_ip().unwrap());
        let state = Arc::new(Mutex::new(State { token: token.into(), ..Default::default() }));
        let (s, st) = (server.clone(), state.clone());
        let handle = std::thread::spawn(move || {
            for rq in s.incoming_requests() {
                handle_request(rq, &st);
            }
        });
        MockBackend { server, state, handle: Some(handle), base_url }
    }

    pub fn enqueue(&self, job: Value) {
        self.state.lock().unwrap().queue.push_back(job);
    }
    pub fn reports(&self) -> Vec<Value> {
        self.state.lock().unwrap().reports.clone()
    }
    pub fn report_for(&self, job_id: &str) -> Option<Value> {
        self.reports().into_iter().find(|r| r["job_id"] == job_id)
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
}

impl Drop for MockBackend {
    fn drop(&mut self) {
        self.server.unblock();
        if let Some(h) = self.handle.take() {
            let _ = h.join();
        }
    }
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
        ("POST", ["v1", "bridge", "jobs", _id, "report"]) => {
            let b = body(&mut rq);
            match serde_json::from_slice::<Value>(&b) {
                Ok(v) => {
                    st.reports.push(v);
                    respond(rq, 204, "application/json", vec![], vec![]);
                }
                Err(_) => respond(rq, 400, "application/json", br#"{"error":"bad json"}"#.to_vec(), vec![]),
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
