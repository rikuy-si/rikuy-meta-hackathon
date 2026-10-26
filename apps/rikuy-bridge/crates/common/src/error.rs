use thiserror::Error;

/// Process exit codes shared by every bridge binary (sysexits-style).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ExitCode {
    Ok = 0,
    Failure = 1,
    Usage = 64,
    Protocol = 76,
    /// The device rejected the credential (HTTP 401/403). Never retried:
    /// repeated attempts can lock the device account.
    AuthRejected = 77,
    /// The device route is down (TCP probe failed). Fail fast, no retry storm.
    Unreachable = 69,
}

#[derive(Debug, Error)]
pub enum BridgeError {
    #[error("device rejected the credential (HTTP {status})")]
    AuthRejected { status: u16 },
    #[error("device unreachable: {0}")]
    Unreachable(String),
    #[error("protocol error: {0}")]
    Protocol(String),
    #[error("unsupported: {0}")]
    Unsupported(String),
    #[error("usage: {0}")]
    Usage(String),
    #[error("io: {0}")]
    Io(#[from] std::io::Error),
}

impl BridgeError {
    pub fn exit_code(&self) -> ExitCode {
        match self {
            BridgeError::AuthRejected { .. } => ExitCode::AuthRejected,
            BridgeError::Unreachable(_) => ExitCode::Unreachable,
            BridgeError::Protocol(_) => ExitCode::Protocol,
            BridgeError::Usage(_) => ExitCode::Usage,
            BridgeError::Unsupported(_) | BridgeError::Io(_) => ExitCode::Failure,
        }
    }

    /// Stable machine-readable code used in reports.
    pub fn code(&self) -> &'static str {
        match self {
            BridgeError::AuthRejected { .. } => "auth_rejected",
            BridgeError::Unreachable(_) => "unreachable",
            BridgeError::Protocol(_) => "protocol",
            BridgeError::Unsupported(_) => "unsupported",
            BridgeError::Usage(_) => "usage",
            BridgeError::Io(_) => "io",
        }
    }
}
