//! Job execution on top of ONVIF: what one command or one backend job becomes.
use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::time::Duration;

use chrono::{Duration as CDuration, NaiveDateTime};
use rikuy_bridge_common::liveness::probe;
use rikuy_bridge_common::{Artifact, ArtifactKind, BridgeError, Credential};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::media;
use crate::onvif::{self, OnvifDevice, Profile, RecordingInfo};
use crate::rtsp::{self, Replay, Tools};

pub const DOWNLOAD_RETRIES: u32 = 2;
const MAX_SNAPSHOT: u64 = 20 * 1024 * 1024;

#[derive(Debug, Clone)]
pub struct Options {
    pub tools: Tools,
    /// Recordings are cut into files of at most this length (resumable units).
    pub chunk_secs: i64,
    /// Refuse windows longer than this per job.
    pub max_window_secs: i64,
}

impl Default for Options {
    fn default() -> Self {
        Options { tools: Tools::default(), chunk_secs: 900, max_window_secs: 24 * 3600 }
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct Camera {
    /// Track id for search/download: the 1-based channel number.
    pub id: u32,
    pub channel: u32,
    pub enabled: bool,
    pub description: Option<String>,
    pub source_token: String,
    pub profile_token: String,
    pub encoding: Option<String>,
    pub width: Option<u32>,
    pub height: Option<u32>,
    pub recording_token: Option<String>,
    /// Device-local wall-clock times.
    pub earliest: Option<NaiveDateTime>,
    pub latest: Option<NaiveDateTime>,
    pub timezone: Option<String>,
    pub utc_offset_secs: i64,
    pub model: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Segment {
    pub track: u32,
    /// Device-local wall-clock times, as in the bridge contract.
    pub start: NaiveDateTime,
    pub end: NaiveDateTime,
    pub start_utc: NaiveDateTime,
    pub end_utc: NaiveDateTime,
    pub recording_token: String,
}

impl Segment {
    pub fn secs(&self) -> i64 {
        (self.end_utc - self.start_utc).num_seconds()
    }
}

pub struct Session {
    pub dev: OnvifDevice,
    channels: Vec<(String, Profile)>,
    recordings: Option<Vec<RecordingInfo>>,
}

impl Session {
    pub fn open(base_url: &str, credential: Credential) -> Result<Session, BridgeError> {
        let mut dev = OnvifDevice::connect(base_url, credential)?;
        let channels = onvif::channels(&dev.profiles()?);
        Ok(Session { dev, channels, recordings: None })
    }

    fn channel(&self, n: u32) -> Result<&(String, Profile), BridgeError> {
        n.checked_sub(1)
            .and_then(|i| self.channels.get(i as usize))
            .ok_or_else(|| BridgeError::Usage(format!("channel {n} does not exist (device has {})", self.channels.len())))
    }

    fn recordings(&mut self) -> Result<&[RecordingInfo], BridgeError> {
        if self.recordings.is_none() {
            let r = if self.dev.has_service(onvif::NS_SEARCH) { self.dev.recordings()? } else { vec![] };
            self.recordings = Some(r);
        }
        Ok(self.recordings.as_deref().unwrap())
    }

    /// The recording that belongs to a channel: matched by source token, or by
    /// position when the device does not name sources.
    fn recording_for(&mut self, channel: u32) -> Result<Option<RecordingInfo>, BridgeError> {
        let source = self.channel(channel)?.0.clone();
        let n_channels = self.channels.len();
        let recs = self.recordings()?;
        if let Some(r) = recs.iter().find(|r| r.source_id.as_deref() == Some(source.as_str())) {
            return Ok(Some(r.clone()));
        }
        let any_named = recs.iter().any(|r| r.source_id.is_some());
        if !any_named && recs.len() == n_channels {
            return Ok(recs.get(channel as usize - 1).cloned());
        }
        Ok(None)
    }

    pub fn cameras(&mut self) -> Result<Vec<Camera>, BridgeError> {
        let mut out = Vec::new();
        for i in 0..self.channels.len() {
            let ch = i as u32 + 1;
            let rec = self.recording_for(ch)?;
            let (source, p) = self.channel(ch)?.clone();
            let clock = &self.dev.clock;
            out.push(Camera {
                id: ch,
                channel: ch,
                enabled: true,
                description: rec.as_ref().and_then(|r| r.name.clone()).or_else(|| p.name.clone()),
                source_token: source,
                profile_token: p.token.clone(),
                encoding: p.encoding.clone(),
                width: p.width,
                height: p.height,
                recording_token: rec.as_ref().map(|r| r.token.clone()),
                earliest: rec.as_ref().and_then(|r| r.earliest_utc).map(|t| clock.to_local(t)),
                latest: rec.as_ref().and_then(|r| r.latest_utc).map(|t| clock.to_local(t)),
                timezone: clock.tz_string.clone(),
                utc_offset_secs: clock.offset_now(),
                model: self.dev.info.model.clone(),
            });
        }
        Ok(out)
    }

    pub fn snapshot(&mut self, channel: u32, out: &Path) -> Result<Artifact, BridgeError> {
        let token = self.channel(channel)?.1.token.clone();
        let uri = self.dev.snapshot_uri(&token)?;
        let (jpeg, _ct) = self.dev.soap.get_bytes(&uri, MAX_SNAPSHOT)?;
        if !media::is_jpeg(&jpeg) {
            return Err(BridgeError::Protocol(format!("snapshot channel {channel}: not a complete JPEG")));
        }
        write_atomic(out, &jpeg)?;
        Ok(Artifact {
            kind: ArtifactKind::Snapshot,
            name: file_name(out),
            bytes: jpeg.len() as u64,
            sha256: hex(&Sha256::digest(&jpeg)),
            uploaded: false,
            object_key: None,
        })
    }

    /// Recorded segments in a device-local window, per track (channel).
    pub fn search(&mut self, from: NaiveDateTime, to: NaiveDateTime, tracks: &[u32]) -> Result<Vec<Segment>, BridgeError> {
        if to <= from {
            return Err(BridgeError::Usage("`to` must be after `from`".into()));
        }
        if !self.dev.has_service(onvif::NS_SEARCH) {
            return Err(BridgeError::Unsupported("device has no ONVIF Search service (Profile G)".into()));
        }
        let tracks: Vec<u32> = if tracks.is_empty() { (1..=self.channels.len() as u32).collect() } else { tracks.to_vec() };
        let (from_utc, to_utc) = (self.dev.clock.to_utc(from), self.dev.clock.to_utc(to));
        let mut out = Vec::new();
        for t in tracks {
            let Some(rec) = self.recording_for(t)? else { continue };
            let events = match self.dev.track_events(&rec.token, from_utc, to_utc) {
                Ok(e) => e,
                // FindEvents is optional in practice; fall back to the recording span.
                Err(BridgeError::Unsupported(_)) => vec![],
                Err(e) => return Err(e),
            };
            let events: Vec<_> = events.into_iter().collect();
            for (s, e) in onvif::recorded_ranges(&events, from_utc, to_utc, rec.earliest_utc, rec.latest_utc) {
                out.push(Segment {
                    track: t,
                    start: self.dev.clock.to_local(s),
                    end: self.dev.clock.to_local(e),
                    start_utc: s,
                    end_utc: e,
                    recording_token: rec.token.clone(),
                });
            }
        }
        Ok(out)
    }

    pub fn download_range(
        &mut self,
        opts: &Options,
        from: NaiveDateTime,
        to: NaiveDateTime,
        tracks: &[u32],
        out_dir: &Path,
    ) -> Result<DownloadSummary, BridgeError> {
        if (to - from).num_seconds() > opts.max_window_secs {
            return Err(BridgeError::Usage(format!("window longer than {}s; split the request", opts.max_window_secs)));
        }
        fs::create_dir_all(out_dir)?;
        let segments = self.search(from, to, tracks)?;
        let chunks: Vec<Segment> = segments.iter().flat_map(|s| chunk(s, opts.chunk_secs)).collect();
        let mut summary = DownloadSummary { found: chunks.len(), ..Default::default() };
        let mut manifest = Manifest::load(out_dir);
        let mut uris: BTreeMap<String, url::Url> = BTreeMap::new();
        for c in &chunks {
            let name = recording_file_name(c);
            let path = out_dir.join(&name);
            let expected = c.secs() as f64;
            // Resume: a complete, valid file is kept and not requested again.
            if path.exists() {
                if let Ok(info) = media::probe(&opts.tools.ffprobe, &path) {
                    if media::duration_ok(info.duration_secs, expected) {
                        let (bytes, sha256) = (fs::metadata(&path)?.len(), sha256_file(&path)?);
                        manifest.entries.insert(name.clone(), ManifestEntry::new(c, bytes, &sha256, &info));
                        summary.skipped += 1;
                        summary.artifacts.push(recording_artifact(name, bytes, sha256));
                        continue;
                    }
                }
            }
            if !uris.contains_key(&c.recording_token) {
                match self.dev.replay_uri(&c.recording_token) {
                    Ok(u) => {
                        uris.insert(c.recording_token.clone(), u);
                    }
                    Err(e) => {
                        summary.error = Some(e);
                        break;
                    }
                }
            }
            let uri = uris[&c.recording_token].clone();
            match self.fetch_chunk(opts, &uri, c, &path) {
                Ok(info) => {
                    let (bytes, sha256) = (fs::metadata(&path)?.len(), sha256_file(&path)?);
                    manifest.entries.insert(name.clone(), ManifestEntry::new(c, bytes, &sha256, &info));
                    summary.artifacts.push(recording_artifact(name, bytes, sha256));
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

    fn fetch_chunk(&mut self, opts: &Options, uri: &url::Url, c: &Segment, path: &Path) -> Result<media::MediaInfo, BridgeError> {
        let part = path.with_extension("mp4.part");
        let timeout = Duration::from_secs((c.secs().max(1) as u64) * 4 + 60);
        let mut attempt = 0;
        loop {
            let replay = Replay { uri, start_utc: c.start_utc, end_utc: c.end_utc, credential: &self.dev.soap.credential };
            let r = rtsp::capture(&opts.tools, &replay, &part, timeout).and_then(|_| {
                let info = media::probe(&opts.tools.ffprobe, &part)?;
                if !media::duration_ok(info.duration_secs, c.secs() as f64) {
                    return Err(BridgeError::Protocol(format!(
                        "{}: got {:.1}s of video, expected {}s",
                        file_name(path),
                        info.duration_secs,
                        c.secs()
                    )));
                }
                Ok(info)
            });
            match r {
                Ok(info) => {
                    fs::rename(&part, path)?;
                    return Ok(info);
                }
                Err(BridgeError::AuthRejected { status }) => {
                    let _ = fs::remove_file(&part);
                    return Err(self.dev.soap.poison(status));
                }
                Err(BridgeError::Unreachable(msg)) if attempt < DOWNLOAD_RETRIES => {
                    let _ = fs::remove_file(&part);
                    attempt += 1;
                    let (host, port) = self.dev.soap.route();
                    if probe(&host, port, Duration::from_secs(3)).is_err() {
                        return Err(BridgeError::Unreachable(msg));
                    }
                    std::thread::sleep(Duration::from_millis(500 * attempt as u64));
                }
                Err(e) => {
                    let _ = fs::remove_file(&part);
                    return Err(e);
                }
            }
        }
    }
}

fn chunk(s: &Segment, max: i64) -> Vec<Segment> {
    let mut out = Vec::new();
    let mut t = s.start_utc;
    while t < s.end_utc {
        let e = (t + CDuration::seconds(max.max(1))).min(s.end_utc);
        let shift = t - s.start_utc;
        let len = e - t;
        out.push(Segment {
            track: s.track,
            start: s.start + shift,
            end: s.start + shift + len,
            start_utc: t,
            end_utc: e,
            recording_token: s.recording_token.clone(),
        });
        t = e;
    }
    out
}

pub fn recording_file_name(c: &Segment) -> String {
    format!("cam{}_{}_{}s.mp4", c.track, c.start.format("%Y%m%dT%H%M%S"), c.secs())
}

fn recording_artifact(name: String, bytes: u64, sha256: String) -> Artifact {
    Artifact { kind: ArtifactKind::Recording, name, bytes, sha256, uploaded: false, object_key: None }
}

#[derive(Debug, Default)]
pub struct DownloadSummary {
    pub artifacts: Vec<Artifact>,
    pub found: usize,
    pub skipped: usize,
    pub error: Option<BridgeError>,
}

#[derive(Debug, Default, Serialize, Deserialize)]
pub struct Manifest {
    pub entries: BTreeMap<String, ManifestEntry>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ManifestEntry {
    pub track: u32,
    pub start: NaiveDateTime,
    pub end: NaiveDateTime,
    pub start_utc: NaiveDateTime,
    pub end_utc: NaiveDateTime,
    pub recording_token: String,
    pub bytes: u64,
    pub sha256: String,
    pub duration_secs: f64,
    pub video_codec: String,
    pub audio_codec: Option<String>,
}

impl ManifestEntry {
    fn new(c: &Segment, bytes: u64, sha256: &str, info: &media::MediaInfo) -> Self {
        ManifestEntry {
            track: c.track,
            start: c.start,
            end: c.end,
            start_utc: c.start_utc,
            end_utc: c.end_utc,
            recording_token: c.recording_token.clone(),
            bytes,
            sha256: sha256.to_string(),
            duration_secs: info.duration_secs,
            video_codec: info.video_codec.clone(),
            audio_codec: info.audio_codec.clone(),
        }
    }
}

impl Manifest {
    pub fn load(dir: &Path) -> Manifest {
        fs::read(dir.join("manifest.json")).ok().and_then(|b| serde_json::from_slice(&b).ok()).unwrap_or_default()
    }

    pub fn save(&self, dir: &Path) -> Result<(), BridgeError> {
        let mut merged = Manifest::load(dir);
        for (k, v) in &self.entries {
            merged.entries.insert(k.clone(), v.clone());
        }
        merged.entries.retain(|k, _| dir.join(k).exists());
        let data = serde_json::to_vec_pretty(&merged).map_err(|e| BridgeError::Protocol(e.to_string()))?;
        write_atomic(&dir.join("manifest.json"), &data)
    }
}

pub fn write_atomic(path: &Path, data: &[u8]) -> Result<(), BridgeError> {
    if let Some(dir) = path.parent() {
        if !dir.as_os_str().is_empty() {
            fs::create_dir_all(dir)?;
        }
    }
    let mut tmp = path.as_os_str().to_owned();
    tmp.push(format!(".tmp-{}", std::process::id()));
    let tmp = PathBuf::from(tmp);
    fs::write(&tmp, data)?;
    fs::rename(&tmp, path)?;
    Ok(())
}

fn file_name(p: &Path) -> String {
    p.file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_default()
}

pub fn hex(b: &[u8]) -> String {
    b.iter().map(|x| format!("{x:02x}")).collect()
}

pub fn sha256_file(p: &Path) -> Result<String, BridgeError> {
    let mut f = fs::File::open(p)?;
    let mut h = Sha256::new();
    std::io::copy(&mut f, &mut h)?;
    Ok(hex(&h.finalize()))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn t(s: &str) -> NaiveDateTime {
        NaiveDateTime::parse_from_str(s, "%Y-%m-%dT%H:%M:%S").unwrap()
    }

    #[test]
    fn chunks_keep_local_and_utc_aligned() {
        let s = Segment {
            track: 1,
            start: t("2026-10-30T10:00:00"),
            end: t("2026-10-30T10:25:00"),
            start_utc: t("2026-10-30T14:00:00"),
            end_utc: t("2026-10-30T14:25:00"),
            recording_token: "R1".into(),
        };
        let c = chunk(&s, 600);
        assert_eq!(c.len(), 3);
        assert_eq!(c[2].start, t("2026-10-30T10:20:00"));
        assert_eq!(c[2].start_utc, t("2026-10-30T14:20:00"));
        assert_eq!(c[2].secs(), 300);
        assert_eq!(recording_file_name(&c[0]), "cam1_20261030T100000_600s.mp4");
    }
}
