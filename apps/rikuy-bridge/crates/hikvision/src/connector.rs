//! The Hikvision implementation of the bridge's `Connector`.
use std::path::Path;

use rikuy_bridge_common::daemon::{Connector, JobOutcome, Produced};
use rikuy_bridge_common::{Job, JobKind};

use crate::exec;
use crate::isapi::{IsapiClient, Stream};

pub struct HikvisionConnector;

impl Connector for HikvisionConnector {
    fn family(&self) -> &'static str {
        "hikvision"
    }

    fn execute(&mut self, job: &Job, workdir: &Path) -> JobOutcome {
        let mut client = match IsapiClient::new(&job.device.base_url, job.credential.clone()) {
            Ok(c) => c,
            Err(e) => return JobOutcome::err(e),
        };
        let json = |v: serde_json::Result<serde_json::Value>| v.ok();
        match &job.kind {
            JobKind::ListCameras => match client.tracks() {
                Ok(t) => JobOutcome { data: json(serde_json::to_value(t)), ..Default::default() },
                Err(e) => JobOutcome::err(e),
            },
            JobKind::Search { from, to, tracks } => match client.search(*from, *to, tracks) {
                Ok(r) => JobOutcome { data: json(serde_json::to_value(r)), ..Default::default() },
                Err(e) => JobOutcome::err(e),
            },
            JobKind::Snapshot { channel } => {
                let path = workdir.join(format!("snapshot-cam{channel}.jpg"));
                match exec::snapshot(&mut client, *channel, Stream::Main, &path) {
                    Ok(artifact) => JobOutcome {
                        produced: vec![Produced { artifact, path, upload: Some("image/jpeg") }],
                        ..Default::default()
                    },
                    Err(e) => JobOutcome::err(e),
                }
            }
            JobKind::Download { from, to, tracks } => match exec::download_range(&mut client, *from, *to, tracks, workdir) {
                Ok(s) => JobOutcome {
                    data: Some(serde_json::json!({ "found": s.found, "skipped_existing": s.skipped })),
                    produced: s
                        .artifacts
                        .into_iter()
                        .map(|a| Produced { path: workdir.join(&a.name), artifact: a, upload: None })
                        .collect(),
                    error: s.error,
                },
                Err(e) => JobOutcome::err(e),
            },
        }
    }
}
