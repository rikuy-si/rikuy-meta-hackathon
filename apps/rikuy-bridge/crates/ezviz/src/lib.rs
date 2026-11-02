//! Ezviz connector over ONVIF.
//!
//! The bridge reaches the cameras on the customer LAN through ONVIF:
//! Profile T (Media2) for live snapshots and Profile G (Search + Replay) for
//! recordings. The daemon, backend contract, credential handling and reporting
//! come from `rikuy-bridge-common` unchanged.

pub mod connector;
pub mod exec;
pub mod media;
pub mod onvif;
pub mod rtsp;
pub mod soap;
pub mod tz;
pub mod xml;

pub use connector::EzvizConnector;
