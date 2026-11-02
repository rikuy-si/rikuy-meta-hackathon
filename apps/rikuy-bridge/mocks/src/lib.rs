//! Test doubles for rikuy-bridge.
//!
//! - [`isapi::MockIsapi`]: a Hikvision DVR speaking ISAPI over HTTP with Digest
//!   auth, built from the field-validated protocol reference (paged search
//!   capped at 64, POST-only download, IMKH-wrapped recordings, lockout).
//! - [`onvif::MockOnvif`]: an Ezviz camera over ONVIF (Device, Media2, Search,
//!   Replay) with an RTSP replay server streaming real HEVC + AAC.
//! - [`backend::MockBackend`]: the Rikuy backend side of the bridge contract
//!   (job queue, report sink, snapshot sink, presigned upload grants).
//! - [`objstore::MockObjectStore`]: an R2 stand-in that only accepts uploads
//!   through valid, unexpired presigned PUT URLs with an exact Content-Length.

pub mod backend;
pub mod digest;
pub mod isapi;
pub mod media;
pub mod onvif;
pub mod objstore;
pub(crate) mod http;
