use serde::{Deserialize, Deserializer, Serialize};
use zeroize::Zeroize;

/// A secret string that never prints and is wiped from memory on drop.
/// It deliberately does not implement `Serialize`: a secret can come in from
/// the backend, but the bridge has no code path that writes it back out.
#[derive(Clone, Default)]
pub struct Secret(String);

impl Secret {
    pub fn new(value: impl Into<String>) -> Self {
        Secret(value.into())
    }
    pub fn expose(&self) -> &str {
        &self.0
    }
}

impl Drop for Secret {
    fn drop(&mut self) {
        self.0.zeroize();
    }
}

impl std::fmt::Debug for Secret {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("Secret(***)")
    }
}

impl<'de> Deserialize<'de> for Secret {
    fn deserialize<D: Deserializer<'de>>(d: D) -> Result<Self, D::Error> {
        String::deserialize(d).map(Secret)
    }
}

/// Device credential, provisioned by the backend per job.
#[derive(Debug, Clone, Deserialize)]
pub struct Credential {
    pub username: String,
    pub password: Secret,
}

/// Non-secret summary of a credential, safe to log and report.
#[derive(Debug, Clone, Serialize, PartialEq, Eq, Hash)]
pub struct CredentialRef {
    pub username: String,
}
