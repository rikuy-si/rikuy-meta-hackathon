//! Shared contract for every rikuy-bridge connector.
//!
//! A bridge is a small binary that runs on the customer's network, next to the
//! cameras. The Rikuy backend decides *what* to fetch and provisions the device
//! credential per job; the bridge executes the job against the device and
//! reports back. Device families (Hikvision, Ezviz, ...) differ only in how a
//! job is executed ([`daemon::Connector`]), so everything else lives here.

pub mod backend;
pub mod daemon;
pub mod digest;
pub mod error;
pub mod job;
pub mod liveness;
pub mod report;
pub mod secret;
pub mod upload;

pub use error::{BridgeError, ExitCode};
pub use job::{DeviceRef, Job, JobKind};
pub use report::{Artifact, ArtifactKind, JobStatus, Report};
pub use secret::{Credential, Secret};
