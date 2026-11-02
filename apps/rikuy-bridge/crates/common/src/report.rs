use serde::Serialize;

/// Result of a job, sent back to the backend. Never contains the credential.
#[derive(Debug, Clone, Serialize)]
pub struct Report {
    pub job_id: String,
    pub bridge: String,
    pub family: String,
    pub status: JobStatus,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error_code: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error_message: Option<String>,
    pub artifacts: Vec<Artifact>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub data: Option<serde_json::Value>,
}

#[derive(Debug, Clone, Copy, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum JobStatus {
    Succeeded,
    /// Some artifacts were produced before a fatal error.
    Partial,
    Failed,
    AuthRejected,
}

#[derive(Debug, Clone, Serialize)]
pub struct Artifact {
    pub kind: ArtifactKind,
    pub name: String,
    pub bytes: u64,
    pub sha256: String,
    /// True once the bytes were PUT to the backend; otherwise they stay in the
    /// bridge spool directory.
    #[serde(default)]
    pub uploaded: bool,
    /// Object-storage key the backend assigned, once the bytes are stored there.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub object_key: Option<String>,
}

#[derive(Debug, Clone, Copy, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ArtifactKind {
    Snapshot,
    Recording,
}
