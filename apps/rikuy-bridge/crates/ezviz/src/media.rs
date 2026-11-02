//! Media validation: a recording is only reported once ffprobe agrees it is a
//! complete, decodable container of the expected length.
use std::path::Path;
use std::process::Command;

use rikuy_bridge_common::BridgeError;
use serde::Serialize;

#[derive(Debug, Clone, Serialize)]
pub struct MediaInfo {
    pub duration_secs: f64,
    pub video_codec: String,
    pub width: Option<u32>,
    pub height: Option<u32>,
    pub audio_codec: Option<String>,
}

pub fn probe(ffprobe: &Path, file: &Path) -> Result<MediaInfo, BridgeError> {
    let out = Command::new(ffprobe)
        .args(["-v", "error", "-show_entries", "format=duration:stream=codec_type,codec_name,width,height", "-of", "json"])
        .arg(file)
        .output()
        .map_err(|e| BridgeError::Usage(format!("cannot run {}: {e}", ffprobe.display())))?;
    if !out.status.success() {
        return Err(BridgeError::Protocol(format!(
            "{}: not a readable media file: {}",
            file.display(),
            String::from_utf8_lossy(&out.stderr).trim()
        )));
    }
    let v: serde_json::Value =
        serde_json::from_slice(&out.stdout).map_err(|e| BridgeError::Protocol(format!("ffprobe json: {e}")))?;
    let streams = v["streams"].as_array().cloned().unwrap_or_default();
    let video = streams
        .iter()
        .find(|s| s["codec_type"] == "video")
        .ok_or_else(|| BridgeError::Protocol(format!("{}: no video stream", file.display())))?;
    let duration_secs = v["format"]["duration"]
        .as_str()
        .and_then(|d| d.parse().ok())
        .ok_or_else(|| BridgeError::Protocol(format!("{}: no duration", file.display())))?;
    Ok(MediaInfo {
        duration_secs,
        video_codec: video["codec_name"].as_str().unwrap_or("?").to_string(),
        width: video["width"].as_u64().map(|w| w as u32),
        height: video["height"].as_u64().map(|h| h as u32),
        audio_codec: streams.iter().find(|s| s["codec_type"] == "audio").and_then(|s| s["codec_name"].as_str()).map(String::from),
    })
}

/// Accept small container rounding (frame duration, last GOP): 2 s or 2 %.
pub fn duration_ok(actual: f64, expected: f64) -> bool {
    (actual - expected).abs() <= f64::max(2.0, expected * 0.02)
}

pub fn is_jpeg(b: &[u8]) -> bool {
    b.len() > 4 && b[..2] == [0xFF, 0xD8] && b[b.len() - 2..] == [0xFF, 0xD9]
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn tolerance() {
        assert!(duration_ok(119.0, 120.0));
        assert!(!duration_ok(100.0, 120.0));
        assert!(duration_ok(890.0, 900.0));
        assert!(!duration_ok(870.0, 900.0));
    }

    #[test]
    fn jpeg_envelope() {
        assert!(is_jpeg(&[0xFF, 0xD8, 1, 2, 0xFF, 0xD9]));
        assert!(!is_jpeg(b"mock-channel-1"));
    }
}
