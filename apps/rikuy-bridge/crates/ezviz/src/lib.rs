//! Ezviz connector (scaffold).
//!
//! The daemon, backend contract, credential handling and reporting all come
//! from `rikuy-bridge-common` unchanged. Only the device protocol is missing:
//! every job kind is answered `unsupported` until [`client`] is implemented.

pub mod client;

use std::path::Path;

use rikuy_bridge_common::daemon::{Connector, JobOutcome};
use rikuy_bridge_common::{BridgeError, Job, JobKind};

pub struct EzvizConnector;

impl Connector for EzvizConnector {
    fn family(&self) -> &'static str {
        "ezviz"
    }

    fn execute(&mut self, job: &Job, _workdir: &Path) -> JobOutcome {
        let what = match &job.kind {
            JobKind::ListCameras => client::LIST_CAMERAS,
            JobKind::Snapshot { .. } => client::SNAPSHOT,
            JobKind::Search { .. } => client::SEARCH,
            JobKind::Download { .. } => client::DOWNLOAD,
        };
        JobOutcome::err(BridgeError::Unsupported(format!("ezviz {what}: protocol client not implemented yet")))
    }
}
