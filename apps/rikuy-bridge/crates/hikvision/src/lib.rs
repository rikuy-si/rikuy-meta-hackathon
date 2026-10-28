//! Hikvision/HiLook connector: ISAPI client and job executor.

pub mod digest;
pub mod exec;
pub mod isapi;
pub mod xml;

pub use isapi::{IsapiClient, Recording, Track};
