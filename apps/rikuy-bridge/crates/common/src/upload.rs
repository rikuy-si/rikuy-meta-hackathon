//! Deliver large artifacts to object storage (R2) through presigned URLs.
//!
//! The bridge never holds storage credentials and never chooses object keys:
//! it asks the backend for one presigned URL per file, in small batches so
//! URLs do not expire while earlier files are still uploading, and streams
//! each file from the spool with an exact Content-Length.
use std::fs::File;
use std::path::PathBuf;
use std::time::Duration;

use crate::backend::{BackendClient, UploadGrant, UploadGrants, UploadRequest};
use crate::report::Artifact;
use crate::BridgeError;

pub const DEFAULT_BATCH: usize = 16;

pub struct Pending {
    /// Index into the report's artifact list.
    pub index: usize,
    pub path: PathBuf,
    pub content_type: &'static str,
}

#[derive(Debug, Default)]
pub struct UploadSummary {
    pub uploaded: usize,
    pub already_stored: usize,
    pub refreshed_grants: usize,
    /// (artifact name, reason)
    pub failed: Vec<(String, String)>,
    /// The backend has no object storage; files stay in the spool.
    pub unsupported: bool,
}

enum PutError {
    /// The store refused the URL (expired, bad signature): a fresh grant may work.
    Refused(String),
    Other(String),
}

fn agent() -> ureq::Agent {
    // No overall timeout: a recording can take minutes on a slow uplink.
    ureq::AgentBuilder::new()
        .timeout_connect(Duration::from_secs(15))
        .timeout_read(Duration::from_secs(120))
        .timeout_write(Duration::from_secs(120))
        .redirects(0)
        .build()
}

fn put(agent: &ureq::Agent, grant: &UploadGrant, path: &PathBuf) -> Result<(), PutError> {
    let file = File::open(path).map_err(|e| PutError::Other(format!("open: {e}")))?;
    let len = file.metadata().map_err(|e| PutError::Other(format!("stat: {e}")))?.len();
    // Explicit Content-Length: presigned PUTs reject chunked transfer encoding.
    // No Authorization header: the URL itself is the credential.
    let mut rq = agent.request(&grant.method, &grant.url).set("Content-Length", &len.to_string());
    for (k, v) in &grant.headers {
        rq = rq.set(k, v);
    }
    match rq.send(file) {
        Ok(_) => Ok(()),
        Err(ureq::Error::Status(code @ (400 | 401 | 403), resp)) => {
            let body = resp.into_string().unwrap_or_default();
            Err(PutError::Refused(format!("HTTP {code} {}", s3_code(&body))))
        }
        Err(ureq::Error::Status(code, resp)) => {
            let body = resp.into_string().unwrap_or_default();
            Err(PutError::Other(format!("HTTP {code} {}", s3_code(&body))))
        }
        Err(ureq::Error::Transport(t)) => Err(PutError::Other(t.to_string())),
    }
}

/// Pull `<Code>…</Code>` out of an S3-style error body, for logs.
fn s3_code(body: &str) -> String {
    body.split_once("<Code>")
        .and_then(|(_, r)| r.split_once("</Code>"))
        .map(|(c, _)| c.to_string())
        .unwrap_or_default()
}

fn request_for(a: &Artifact, content_type: &str) -> UploadRequest {
    UploadRequest { name: a.name.clone(), bytes: a.bytes, sha256: a.sha256.clone(), content_type: content_type.into() }
}

fn mark(a: &mut Artifact, key: &str) {
    a.uploaded = true;
    a.object_key = Some(key.to_string());
}

pub fn deliver(backend: &BackendClient, job_id: &str, artifacts: &mut [Artifact], pending: Vec<Pending>, batch: usize) -> UploadSummary {
    let agent = agent();
    let mut s = UploadSummary::default();
    for chunk in pending.chunks(batch.max(1)) {
        let reqs: Vec<UploadRequest> = chunk.iter().map(|p| request_for(&artifacts[p.index], p.content_type)).collect();
        let grants: UploadGrants = match backend.request_uploads(job_id, &reqs) {
            Ok(Some(g)) => g,
            Ok(None) => {
                s.unsupported = true;
                return s;
            }
            Err(e) => {
                s.failed.extend(chunk.iter().map(|p| (artifacts[p.index].name.clone(), e.to_string())));
                if matches!(e, BridgeError::AuthRejected { .. } | BridgeError::Unreachable(_)) {
                    // Backend gone or token rejected: do not burn through the rest.
                    for rest in pending.iter().skip_while(|p| p.index != chunk[0].index).skip(chunk.len()) {
                        s.failed.push((artifacts[rest.index].name.clone(), e.to_string()));
                    }
                    return s;
                }
                continue;
            }
        };
        for p in chunk {
            let name = artifacts[p.index].name.clone();
            if let Some(st) = grants.stored.iter().find(|x| x.name == name) {
                mark(&mut artifacts[p.index], &st.key);
                s.already_stored += 1;
                continue;
            }
            let Some(grant) = grants.grants.iter().find(|g| g.name == name) else {
                s.failed.push((name, "backend issued no upload grant".into()));
                continue;
            };
            match put(&agent, grant, &p.path) {
                Ok(()) => {
                    mark(&mut artifacts[p.index], &grant.key);
                    s.uploaded += 1;
                }
                Err(PutError::Refused(why)) => {
                    // Expired or rejected URL: ask once more for this file only.
                    s.refreshed_grants += 1;
                    let retry = backend.request_uploads(job_id, &[request_for(&artifacts[p.index], p.content_type)]);
                    match retry {
                        Ok(Some(g)) => {
                            if let Some(st) = g.stored.first() {
                                mark(&mut artifacts[p.index], &st.key);
                                s.already_stored += 1;
                            } else if let Some(fresh) = g.grants.first() {
                                match put(&agent, fresh, &p.path) {
                                    Ok(()) => {
                                        mark(&mut artifacts[p.index], &fresh.key);
                                        s.uploaded += 1;
                                    }
                                    Err(PutError::Refused(e) | PutError::Other(e)) => s.failed.push((name, format!("{why}; retry: {e}"))),
                                }
                            } else {
                                s.failed.push((name, format!("{why}; no fresh grant")));
                            }
                        }
                        Ok(None) => s.failed.push((name, format!("{why}; object storage withdrawn"))),
                        Err(e) => s.failed.push((name, format!("{why}; {e}"))),
                    }
                }
                Err(PutError::Other(e)) => s.failed.push((name, e)),
            }
        }
    }
    s
}
