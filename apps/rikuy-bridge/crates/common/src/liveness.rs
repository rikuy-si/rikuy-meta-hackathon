//! Route liveness: probe the device's TCP port before every request so a dead
//! route fails fast instead of feeding a blind retry loop.
use std::net::{TcpStream, ToSocketAddrs};
use std::time::Duration;

use crate::BridgeError;

pub const DEFAULT_PROBE_TIMEOUT: Duration = Duration::from_secs(3);

pub fn probe(host: &str, port: u16, timeout: Duration) -> Result<(), BridgeError> {
    let addrs = (host, port)
        .to_socket_addrs()
        .map_err(|e| BridgeError::Unreachable(format!("{host}:{port}: resolve failed: {e}")))?;
    let mut last = None;
    for addr in addrs {
        match TcpStream::connect_timeout(&addr, timeout) {
            Ok(_) => return Ok(()),
            Err(e) => last = Some(e),
        }
    }
    Err(BridgeError::Unreachable(format!(
        "{host}:{port}: {}",
        last.map(|e| e.to_string()).unwrap_or_else(|| "no address".into())
    )))
}
