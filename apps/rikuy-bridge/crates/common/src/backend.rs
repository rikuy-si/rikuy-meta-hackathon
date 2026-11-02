//! Client for the Rikuy backend side of the bridge contract.
//! See docs/backend-contract.md.
use std::io::Read;
use std::time::Duration;

use serde::{Deserialize, Serialize};
use url::Url;

use crate::{BridgeError, Report};

/// One file the bridge wants to deliver to object storage.
#[derive(Debug, Clone, Serialize)]
pub struct UploadRequest {
    pub name: String,
    pub bytes: u64,
    pub sha256: String,
    pub content_type: String,
}

/// A presigned upload: send exactly \`method url\` with \`headers\` and the body.
#[derive(Debug, Clone, Deserialize)]
pub struct UploadGrant {
    pub name: String,
    pub key: String,
    #[serde(default = "put")]
    pub method: String,
    pub url: String,
    #[serde(default)]
    pub headers: std::collections::BTreeMap<String, String>,
    #[serde(default)]
    pub expires_at: Option<i64>,
}

fn put() -> String {
    "PUT".into()
}

/// Already present and verified in object storage: nothing to send.
#[derive(Debug, Clone, Deserialize)]
pub struct StoredObject {
    pub name: String,
    pub key: String,
}

#[derive(Debug, Clone, Deserialize, Default)]
pub struct UploadGrants {
    #[serde(default)]
    pub grants: Vec<UploadGrant>,
    #[serde(default)]
    pub stored: Vec<StoredObject>,
}

#[derive(Deserialize, Default)]
struct ReportAck {
    #[serde(default)]
    delete: Vec<String>,
}

pub struct BackendClient {
    base: Url,
    token: crate::Secret,
    bridge_id: String,
    agent: ureq::Agent,
}

/// A job as received: kept raw until parsed, so malformed jobs can still be
/// reported against their id.
pub type RawJob = serde_json::Value;

impl BackendClient {
    pub fn new(base_url: &str, token: crate::Secret, bridge_id: &str) -> Result<Self, BridgeError> {
        let mut base = Url::parse(base_url).map_err(|e| BridgeError::Usage(format!("bad backend url {base_url}: {e}")))?;
        if !base.path().ends_with('/') {
            let p = format!("{}/", base.path());
            base.set_path(&p);
        }
        let agent = ureq::AgentBuilder::new()
            .timeout_connect(Duration::from_secs(10))
            .timeout(Duration::from_secs(120))
            .build();
        Ok(BackendClient { base, token, bridge_id: bridge_id.into(), agent })
    }

    pub fn bridge_id(&self) -> &str {
        &self.bridge_id
    }

    fn url(&self, segments: &[&str]) -> Url {
        let mut u = self.base.clone();
        {
            let mut p = u.path_segments_mut().expect("base url");
            p.pop_if_empty();
            for s in segments {
                p.push(s); // percent-encodes, so a job id cannot escape the path
            }
        }
        u
    }

    fn auth(&self) -> String {
        format!("Bearer {}", self.token.expose())
    }

    fn map_err(&self, what: &str, e: ureq::Error) -> BridgeError {
        match e {
            ureq::Error::Status(401, _) | ureq::Error::Status(403, _) => BridgeError::AuthRejected { status: 401 },
            ureq::Error::Status(code, _) => BridgeError::Protocol(format!("backend {what}: HTTP {code}")),
            ureq::Error::Transport(t) => BridgeError::Unreachable(format!("backend {what}: {t}")),
        }
    }

    /// `GET v1/bridge/jobs/next?bridge=<id>`: 200 with a job, 204 when idle.
    pub fn next_job(&self) -> Result<Option<RawJob>, BridgeError> {
        let mut u = self.url(&["v1", "bridge", "jobs", "next"]);
        u.query_pairs_mut().append_pair("bridge", &self.bridge_id);
        let resp = self.agent.request_url("GET", &u).set("Authorization", &self.auth()).call().map_err(|e| self.map_err("poll", e))?;
        if resp.status() == 204 {
            return Ok(None);
        }
        let mut s = String::new();
        resp.into_reader().take(4 * 1024 * 1024).read_to_string(&mut s)?;
        serde_json::from_str(&s).map(Some).map_err(|e| BridgeError::Protocol(format!("backend job json: {e}")))
    }

    /// `POST v1/bridge/jobs/<id>/report`. Returns the artifact names the backend
    /// verified in object storage and allows the bridge to delete locally.
    pub fn report(&self, report: &Report) -> Result<Vec<String>, BridgeError> {
        let u = self.url(&["v1", "bridge", "jobs", &report.job_id, "report"]);
        let resp = self
            .agent
            .request_url("POST", &u)
            .set("Authorization", &self.auth())
            .send_json(report)
            .map_err(|e| self.map_err("report", e))?;
        if resp.status() == 204 {
            return Ok(vec![]);
        }
        let ack: ReportAck = resp.into_json().unwrap_or_default();
        Ok(ack.delete)
    }

    /// `POST v1/bridge/jobs/<id>/uploads`: ask for presigned upload URLs.
    /// `Ok(None)` means the backend offers no object storage (404).
    pub fn request_uploads(&self, job_id: &str, files: &[UploadRequest]) -> Result<Option<UploadGrants>, BridgeError> {
        let u = self.url(&["v1", "bridge", "jobs", job_id, "uploads"]);
        let body = serde_json::json!({ "bridge": self.bridge_id, "artifacts": files });
        match self.agent.request_url("POST", &u).set("Authorization", &self.auth()).send_json(body) {
            Ok(resp) => resp
                .into_json::<UploadGrants>()
                .map(Some)
                .map_err(|e| BridgeError::Protocol(format!("backend uploads json: {e}"))),
            Err(ureq::Error::Status(404, _)) => Ok(None),
            Err(e) => Err(self.map_err("uploads", e)),
        }
    }

    /// `PUT v1/bridge/jobs/<id>/artifacts/<name>`
    pub fn upload(&self, job_id: &str, name: &str, content_type: &str, bytes: &[u8]) -> Result<(), BridgeError> {
        let u = self.url(&["v1", "bridge", "jobs", job_id, "artifacts", name]);
        self.agent
            .request_url("PUT", &u)
            .set("Authorization", &self.auth())
            .set("Content-Type", content_type)
            .send_bytes(bytes)
            .map(|_| ())
            .map_err(|e| self.map_err("upload", e))
    }
}
