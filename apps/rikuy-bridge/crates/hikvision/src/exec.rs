//! Job execution on top of the ISAPI client: what a single command or a
//! backend job turns into.
use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};

use chrono::NaiveDateTime;
use rikuy_bridge_common::liveness::probe;
use rikuy_bridge_common::{Artifact, ArtifactKind, BridgeError};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::isapi::{hex, IsapiClient, Recording, Stream};

/// Transient read failures get this many extra attempts per recording, and
/// only while the route still answers the liveness probe.
pub const DOWNLOAD_RETRIES: u32 = 2;

pub fn recording_file_name(rec: &Recording, index: usize) -> String {
    format!("track-{}_{}_{:05}.dav", rec.track, rec.start.format("%Y%m%dT%H%M%S"), index)
}

pub fn snapshot(client: &mut IsapiClient, camera: u32, stream: Stream, out: &Path) -> Result<Artifact, BridgeError> {
    let jpeg = client.snapshot(camera, stream)?;
    write_atomic(out, &jpeg)?;
    Ok(Artifact {
        kind: ArtifactKind::Snapshot,
        name: file_name(out),
        bytes: jpeg.len() as u64,
        sha256: hex(&Sha256::digest(&jpeg)),
    })
}

#[derive(Debug, Default)]
pub struct DownloadSummary {
    pub artifacts: Vec<Artifact>,
    pub found: usize,
    pub skipped: usize,
    /// First fatal error; the remaining recordings were not attempted.
    pub error: Option<BridgeError>,
}

/// Search the window and download every recording into `out_dir`.
/// Auth rejection and a dead route abort the whole run immediately.
pub fn download_range(
    client: &mut IsapiClient,
    from: NaiveDateTime,
    to: NaiveDateTime,
    tracks: &[u32],
    out_dir: &Path,
) -> Result<DownloadSummary, BridgeError> {
    fs::create_dir_all(out_dir)?;
    let recs = client.search(from, to, tracks)?;
    let mut summary = DownloadSummary { found: recs.len(), ..Default::default() };
    let mut manifest = Manifest::load(out_dir);
    for (i, rec) in recs.iter().enumerate() {
        let name = recording_file_name(rec, i + 1);
        let path = out_dir.join(&name);
        let mut attempt = 0;
        let outcome = loop {
            match client.download(rec, &path) {
                Err(BridgeError::Unreachable(msg)) if attempt < DOWNLOAD_RETRIES => {
                    attempt += 1;
                    // Retry only if the route is alive; otherwise stop the run.
                    let (host, port) = route_of(client);
                    if probe(&host, port, std::time::Duration::from_secs(3)).is_err() {
                        break Err(BridgeError::Unreachable(msg));
                    }
                    std::thread::sleep(std::time::Duration::from_millis(500 * attempt as u64));
                }
                other => break other,
            }
        };
        match outcome {
            Ok(d) => {
                if d.skipped {
                    summary.skipped += 1;
                }
                manifest.entries.insert(
                    name.clone(),
                    ManifestEntry {
                        track: rec.track,
                        start: rec.start,
                        end: rec.end,
                        playback_uri: rec.playback_uri.clone(),
                        bytes: d.bytes,
                        sha256: d.sha256.clone(),
                    },
                );
                summary.artifacts.push(Artifact { kind: ArtifactKind::Recording, name, bytes: d.bytes, sha256: d.sha256 });
            }
            Err(e) => {
                summary.error = Some(e);
                break;
            }
        }
    }
    manifest.save(out_dir)?;
    Ok(summary)
}

fn route_of(client: &IsapiClient) -> (String, u16) {
    client.route()
}

fn file_name(p: &Path) -> String {
    p.file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_default()
}

pub fn write_atomic(path: &Path, data: &[u8]) -> Result<(), BridgeError> {
    if let Some(dir) = path.parent() {
        if !dir.as_os_str().is_empty() {
            fs::create_dir_all(dir)?;
        }
    }
    let tmp = tmp_path(path);
    fs::write(&tmp, data)?;
    fs::rename(&tmp, path)?;
    Ok(())
}

fn tmp_path(path: &Path) -> PathBuf {
    let mut s = path.as_os_str().to_owned();
    s.push(format!(".tmp-{}", std::process::id()));
    PathBuf::from(s)
}

/// `manifest.json` in the output directory: merged by file name and written
/// atomically, so concurrent or repeated runs never drop each other's entries
/// for files that are on disk.
#[derive(Debug, Default, Serialize, Deserialize)]
pub struct Manifest {
    pub entries: BTreeMap<String, ManifestEntry>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ManifestEntry {
    pub track: u32,
    pub start: NaiveDateTime,
    pub end: NaiveDateTime,
    pub playback_uri: String,
    pub bytes: u64,
    pub sha256: String,
}

impl Manifest {
    pub fn load(dir: &Path) -> Manifest {
        fs::read(dir.join("manifest.json"))
            .ok()
            .and_then(|b| serde_json::from_slice(&b).ok())
            .unwrap_or_default()
    }

    pub fn save(&self, dir: &Path) -> Result<(), BridgeError> {
        // Re-read and merge just before writing to keep entries another run added.
        let mut merged = Manifest::load(dir);
        for (k, v) in &self.entries {
            merged.entries.insert(k.clone(), v.clone());
        }
        merged.entries.retain(|k, _| dir.join(k).exists());
        let data = serde_json::to_vec_pretty(&merged).map_err(|e| BridgeError::Protocol(e.to_string()))?;
        write_atomic(&dir.join("manifest.json"), &data)
    }
}
