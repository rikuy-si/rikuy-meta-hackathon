//! Test doubles for rikuy-bridge.
//!
//! - [`isapi::MockIsapi`]: a Hikvision DVR speaking ISAPI over HTTP with Digest
//!   auth, built from the field-validated protocol reference (paged search
//!   capped at 64, POST-only download, IMKH-wrapped recordings, lockout).
//! - [`backend::MockBackend`]: the Rikuy backend side of the bridge contract
//!   (job queue, report sink, artifact sink).

pub mod backend;
pub mod digest;
pub mod isapi;
pub(crate) mod http;
