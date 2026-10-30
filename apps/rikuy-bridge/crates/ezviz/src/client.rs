//! Ezviz protocol client: integration points, not implemented.
//!
//! Each constant names one job kind the connector must serve. The notes are
//! candidate approaches to verify on a real device, not validated facts.
//!
//! TODO(list_cameras): enumerate cameras/channels reachable from this host.
//!   Candidate: the account's device list through the Ezviz cloud API, or LAN
//!   discovery when the cameras expose a local interface.
//! TODO(snapshot): capture a live JPEG for one camera.
//!   Candidate: a cloud "capture" call per device serial and channel; or a
//!   frame grabbed from the camera's LAN RTSP stream (device verification code
//!   as the credential).
//! TODO(search): list recordings (SD card or cloud) for a local-time window.
//! TODO(download): fetch recordings for a window into the job's work directory,
//!   validate them, and return `Artifact`s exactly as the Hikvision connector does.
//!
//! Whatever the transport, credentials keep arriving per job through
//! `rikuy_bridge_common::Credential` and must never be persisted.

pub const LIST_CAMERAS: &str = "list_cameras";
pub const SNAPSHOT: &str = "snapshot";
pub const SEARCH: &str = "search";
pub const DOWNLOAD: &str = "download";
