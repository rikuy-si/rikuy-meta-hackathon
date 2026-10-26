use chrono::NaiveDateTime;
use serde::Deserialize;

use crate::secret::Credential;

/// A unit of work handed to the bridge by the backend.
#[derive(Debug, Clone, Deserialize)]
pub struct Job {
    pub id: String,
    pub device: DeviceRef,
    /// Provisioned per job; held in memory only.
    pub credential: Credential,
    #[serde(flatten)]
    pub kind: JobKind,
}

#[derive(Debug, Clone, Deserialize)]
pub struct DeviceRef {
    /// Connector family, e.g. "hikvision" or "ezviz".
    pub family: String,
    /// Base URL of the device as seen from the bridge, e.g. http://10.0.0.20.
    pub base_url: String,
}

/// Device timestamps are local wall-clock time (see docs/backend-contract.md).
#[derive(Debug, Clone, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum JobKind {
    ListCameras,
    Snapshot { channel: u32 },
    Search { from: NaiveDateTime, to: NaiveDateTime, #[serde(default)] tracks: Vec<u32> },
    Download { from: NaiveDateTime, to: NaiveDateTime, #[serde(default)] tracks: Vec<u32> },
}
