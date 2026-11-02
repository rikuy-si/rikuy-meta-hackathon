//! The Ezviz (ONVIF) implementation of the bridge's `Connector`.
use std::path::Path;

use rikuy_bridge_common::daemon::{Connector, Delivery, JobOutcome, Produced};
use rikuy_bridge_common::{Job, JobKind};

use crate::exec::{Options, Session};

#[derive(Default)]
pub struct EzvizConnector {
    pub opts: Options,
}

impl Connector for EzvizConnector {
    fn family(&self) -> &'static str {
        "ezviz"
    }

    fn execute(&mut self, job: &Job, workdir: &Path) -> JobOutcome {
        let mut s = match Session::open(&job.device.base_url, job.credential.clone()) {
            Ok(s) => s,
            Err(e) => return JobOutcome::err(e),
        };
        let json = |v: serde_json::Result<serde_json::Value>| v.ok();
        match &job.kind {
            JobKind::ListCameras => match s.cameras() {
                Ok(c) => JobOutcome { data: json(serde_json::to_value(c)), ..Default::default() },
                Err(e) => JobOutcome::err(e),
            },
            JobKind::Search { from, to, tracks } => match s.search(*from, *to, tracks) {
                Ok(r) => JobOutcome { data: json(serde_json::to_value(r)), ..Default::default() },
                Err(e) => JobOutcome::err(e),
            },
            JobKind::Snapshot { channel } => {
                let path = workdir.join(format!("snapshot-cam{channel}.jpg"));
                match s.snapshot(*channel, &path) {
                    Ok(artifact) => JobOutcome {
                        produced: vec![Produced { artifact, path, delivery: Delivery::Backend("image/jpeg") }],
                        ..Default::default()
                    },
                    Err(e) => JobOutcome::err(e),
                }
            }
            JobKind::Download { from, to, tracks } => match s.download_range(&self.opts, *from, *to, tracks, workdir) {
                Ok(d) => JobOutcome {
                    data: Some(serde_json::json!({ "found": d.found, "skipped_existing": d.skipped })),
                    produced: d
                        .artifacts
                        .into_iter()
                        .map(|a| Produced { path: workdir.join(&a.name), artifact: a, delivery: Delivery::ObjectStore("video/mp4") })
                        .collect(),
                    error: d.error,
                },
                Err(e) => JobOutcome::err(e),
            },
        }
    }
}
