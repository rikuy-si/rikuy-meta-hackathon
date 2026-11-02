//! The bridge daemon: poll the backend, execute jobs with a connector, deliver
//! artifacts, report.
//!
//! Guarantees, whatever the connector:
//! - the device credential arrives with the job, lives in memory for the job's
//!   duration and is zeroized on drop; it is never logged, reported or written;
//! - a credential the device rejected is never sent to that device again: later
//!   jobs carrying it are answered `auth_rejected` without touching the device;
//! - a dead device route backs off before the next poll instead of retrying;
//! - recordings go to object storage through presigned URLs and are deleted
//!   from the spool only after the backend has verified them;
//! - a rejected bridge token stops the daemon (exit 77).
use std::collections::HashSet;
use std::fs;
use std::path::{Path, PathBuf};
use std::time::Duration;

use sha2::{Digest, Sha256};

use crate::backend::{BackendClient, RawJob};
use crate::report::{Artifact, JobStatus, Report};
use crate::upload::{self, Pending};
use crate::{BridgeError, Job};

/// Where a produced artifact should end up.
pub enum Delivery {
    /// Stay in the spool.
    Keep,
    /// PUT straight to the backend (small and latency-sensitive: snapshots).
    Backend(&'static str),
    /// Object storage through a presigned URL (recordings).
    ObjectStore(&'static str),
}

/// Something a connector produced on disk.
pub struct Produced {
    pub artifact: Artifact,
    pub path: PathBuf,
    pub delivery: Delivery,
}

#[derive(Default)]
pub struct JobOutcome {
    pub produced: Vec<Produced>,
    pub data: Option<serde_json::Value>,
    pub error: Option<BridgeError>,
}

impl JobOutcome {
    pub fn err(e: BridgeError) -> Self {
        JobOutcome { error: Some(e), ..Default::default() }
    }
}

/// A device family. Implementations only translate a job into device calls.
pub trait Connector {
    fn family(&self) -> &'static str;
    fn execute(&mut self, job: &Job, workdir: &Path) -> JobOutcome;
}

pub struct DaemonConfig {
    pub spool: PathBuf,
    pub poll_interval: Duration,
    pub unreachable_backoff: Duration,
    pub exit_when_idle: bool,
    /// Presigned URLs requested per batch.
    pub upload_batch: usize,
}

#[derive(Debug, Default)]
pub struct DaemonStats {
    pub jobs: u32,
    pub succeeded: u32,
    pub failed: u32,
}

pub fn run<C: Connector>(connector: &mut C, backend: &BackendClient, cfg: &DaemonConfig) -> Result<DaemonStats, BridgeError> {
    fs::create_dir_all(&cfg.spool)?;
    let mut rejected: HashSet<String> = HashSet::new();
    let mut stats = DaemonStats::default();
    let mut backend_backoff = cfg.poll_interval;
    log(&format!("bridge={} family={} polling", backend.bridge_id(), connector.family()));
    loop {
        let raw = match backend.next_job() {
            Ok(Some(raw)) => {
                backend_backoff = cfg.poll_interval;
                raw
            }
            Ok(None) => {
                if cfg.exit_when_idle {
                    return Ok(stats);
                }
                std::thread::sleep(cfg.poll_interval);
                continue;
            }
            Err(e @ BridgeError::AuthRejected { .. }) => {
                log("backend rejected the bridge token; stopping");
                return Err(e);
            }
            Err(e) => {
                if cfg.exit_when_idle {
                    return Err(e);
                }
                log(&format!("backend unavailable ({}); retrying in {:?}", e.code(), backend_backoff));
                std::thread::sleep(backend_backoff);
                backend_backoff = (backend_backoff * 2).min(Duration::from_secs(300));
                continue;
            }
        };
        stats.jobs += 1;
        let report = handle(connector, backend, cfg, &mut rejected, raw);
        if report.status == JobStatus::Succeeded {
            stats.succeeded += 1;
        } else {
            stats.failed += 1;
        }
        let stored = report.artifacts.iter().filter(|a| a.object_key.is_some()).count();
        log(&format!(
            "job={} status={:?} artifacts={} in_object_store={}{}",
            report.job_id,
            report.status,
            report.artifacts.len(),
            stored,
            report.error_code.as_ref().map(|c| format!(" error={c}")).unwrap_or_default()
        ));
        let unreachable = report.error_code.as_deref() == Some("unreachable");
        match backend.report(&report) {
            Ok(delete) => {
                let n = cleanup(&cfg.spool, &report, &delete);
                if n > 0 {
                    log(&format!("job={} removed {n} verified file(s) from the spool", report.job_id));
                }
            }
            Err(e) => {
                log(&format!("job={} report failed: {e}", report.job_id));
                if matches!(e, BridgeError::AuthRejected { .. }) {
                    return Err(e);
                }
            }
        }
        if unreachable {
            std::thread::sleep(cfg.unreachable_backoff);
        }
    }
}

fn handle<C: Connector>(
    connector: &mut C,
    backend: &BackendClient,
    cfg: &DaemonConfig,
    rejected: &mut HashSet<String>,
    raw: RawJob,
) -> Report {
    let id = raw.get("id").and_then(|v| v.as_str()).unwrap_or("unknown").to_string();
    let mut report = Report {
        job_id: id.clone(),
        bridge: backend.bridge_id().into(),
        family: connector.family().into(),
        status: JobStatus::Failed,
        error_code: None,
        error_message: None,
        artifacts: vec![],
        data: None,
    };
    let fail = |mut r: Report, code: &str, msg: String| {
        r.error_code = Some(code.into());
        r.error_message = Some(msg);
        r
    };
    if !is_safe_id(&id) {
        return fail(report, "invalid_job", "job id must match [A-Za-z0-9_-]{1,128}".into());
    }
    let job: Job = match serde_json::from_value(raw) {
        Ok(j) => j,
        Err(e) => return fail(report, "invalid_job", e.to_string()),
    };
    if job.device.family != connector.family() {
        return fail(report, "unsupported", format!("this bridge serves {}, job is for {}", connector.family(), job.device.family));
    }
    let fp = fingerprint(&job);
    if rejected.contains(&fp) {
        report.status = JobStatus::AuthRejected;
        return fail(report, "auth_rejected", "credential previously rejected by this device; not sent again".into());
    }
    let workdir = cfg.spool.join(&id);
    if let Err(e) = fs::create_dir_all(&workdir) {
        return fail(report, "io", e.to_string());
    }
    let outcome = connector.execute(&job, &workdir);
    drop(job); // zeroize the credential as soon as the device work is done

    let mut to_store = Vec::new();
    for p in outcome.produced {
        let mut a = p.artifact;
        match p.delivery {
            Delivery::Keep => {}
            Delivery::Backend(ct) => {
                match fs::read(&p.path).map_err(BridgeError::from).and_then(|b| backend.upload(&id, &a.name, ct, &b)) {
                    Ok(()) => a.uploaded = true,
                    Err(e) => log(&format!("job={id} upload {} failed: {e}", a.name)),
                }
            }
            Delivery::ObjectStore(ct) => to_store.push(Pending { index: report.artifacts.len(), path: p.path, content_type: ct }),
        }
        report.artifacts.push(a);
    }
    let delivery = if to_store.is_empty() {
        upload::UploadSummary::default()
    } else {
        let s = upload::deliver(backend, &id, &mut report.artifacts, to_store, cfg.upload_batch);
        if s.unsupported {
            log(&format!("job={id} backend offers no object storage; recordings kept in the spool"));
        } else {
            log(&format!(
                "job={id} object storage: {} uploaded, {} already stored, {} refreshed grant(s), {} failed",
                s.uploaded,
                s.already_stored,
                s.refreshed_grants,
                s.failed.len()
            ));
        }
        s
    };
    report.data = outcome.data;
    match outcome.error {
        None if delivery.failed.is_empty() => report.status = JobStatus::Succeeded,
        None => {
            report.status = JobStatus::Partial;
            report.error_code = Some("upload".into());
            report.error_message = Some(
                delivery.failed.iter().map(|(n, why)| format!("{n}: {why}")).collect::<Vec<_>>().join("; "),
            );
        }
        Some(e) => {
            report.status = match &e {
                BridgeError::AuthRejected { .. } => {
                    rejected.insert(fp);
                    JobStatus::AuthRejected
                }
                _ if !report.artifacts.is_empty() => JobStatus::Partial,
                _ => JobStatus::Failed,
            };
            report.error_code = Some(e.code().into());
            report.error_message = Some(e.to_string());
        }
    }
    report
}

/// Delete spool files the backend verified in object storage. Only names that
/// this report marked as uploaded, and only plain file names, are honored.
fn cleanup(spool: &Path, report: &Report, delete: &[String]) -> usize {
    if !is_safe_id(&report.job_id) {
        return 0;
    }
    let dir = spool.join(&report.job_id);
    let mut n = 0;
    for name in delete {
        let ours = report.artifacts.iter().any(|a| &a.name == name && a.uploaded && a.object_key.is_some());
        if ours && is_safe_file_name(name) && fs::remove_file(dir.join(name)).is_ok() {
            n += 1;
        }
    }
    n
}

fn is_safe_id(id: &str) -> bool {
    !id.is_empty() && id.len() <= 128 && id.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'-' || b == b'_')
}

fn is_safe_file_name(name: &str) -> bool {
    !name.is_empty()
        && !name.starts_with('.')
        && name.bytes().all(|b| b.is_ascii_alphanumeric() || matches!(b, b'-' | b'_' | b'.'))
}

/// In-memory only: identifies (device, user, password) without keeping the password.
fn fingerprint(job: &Job) -> String {
    let mut h = Sha256::new();
    h.update(job.device.base_url.as_bytes());
    h.update([0]);
    h.update(job.credential.username.as_bytes());
    h.update([0]);
    h.update(job.credential.password.expose().as_bytes());
    h.finalize().iter().map(|b| format!("{b:02x}")).collect()
}

pub fn log(msg: &str) {
    eprintln!("{} rikuy-bridge: {msg}", chrono::Local::now().format("%Y-%m-%dT%H:%M:%S%z"));
}

#[cfg(test)]
mod tests {
    #[test]
    fn rejects_path_like_ids() {
        assert!(super::is_safe_id("job-42_a"));
        assert!(!super::is_safe_id("../etc"));
        assert!(!super::is_safe_id(""));
        assert!(!super::is_safe_id("a/b"));
    }

    #[test]
    fn only_plain_file_names_are_deleted() {
        assert!(super::is_safe_file_name("track-101_20261029T050000_00001.dav"));
        assert!(!super::is_safe_file_name("../manifest.json"));
        assert!(!super::is_safe_file_name(".hidden"));
        assert!(!super::is_safe_file_name("a/b.dav"));
    }
}
