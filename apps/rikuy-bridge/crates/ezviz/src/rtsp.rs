//! ONVIF replay capture: a local RTSP proxy in front of ffmpeg.
//!
//! ONVIF Profile G replay is plain RTSP plus two things ffmpeg cannot send:
//! `Require: onvif-replay` and an absolute `Range: clock=<utc>-<utc>`. Rather
//! than re-implement RTP depacketizing and MP4 muxing, the bridge runs ffmpeg
//! against a loopback RTSP proxy that:
//!
//! - rewrites the request target to the camera's replay URI;
//! - adds `Require: onvif-replay` to SETUP/PLAY, and replaces PLAY's
//!   `Range` with the absolute clock range plus `Rate-Control: no` (as fast as
//!   the device can send, not real time);
//! - answers the camera's Digest challenge itself, so the device credential
//!   never reaches ffmpeg's argv, environment or logs;
//! - after PLAY, relays the interleaved RTP/RTCP bytes untouched (TCP, so
//!   backpressure and no loss).
//!
//! ffmpeg depacketizes (H.264/H.265/AAC) with the real RTP timestamps and
//! writes MP4 with `-c copy`: no re-encode, original quality.
use std::io::{self, BufRead, BufReader, Read, Write};
use std::net::{Shutdown, TcpListener, TcpStream, ToSocketAddrs};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use chrono::NaiveDateTime;
use rikuy_bridge_common::digest::{Challenge, DigestSession};
use rikuy_bridge_common::{BridgeError, Credential};
use url::Url;

const LOCAL_PATH: &str = "/rikuy-replay";
const HANDSHAKE_TIMEOUT: Duration = Duration::from_secs(20);
const MAX_HEADER_BYTES: usize = 64 * 1024;
const MAX_BODY_BYTES: usize = 1024 * 1024;

#[derive(Debug, Clone)]
pub struct Tools {
    pub ffmpeg: PathBuf,
    pub ffprobe: PathBuf,
}

impl Default for Tools {
    fn default() -> Self {
        Tools {
            ffmpeg: std::env::var_os("RIKUY_FFMPEG").map(PathBuf::from).unwrap_or_else(|| "ffmpeg".into()),
            ffprobe: std::env::var_os("RIKUY_FFPROBE").map(PathBuf::from).unwrap_or_else(|| "ffprobe".into()),
        }
    }
}

pub struct Replay<'a> {
    pub uri: &'a Url,
    pub start_utc: NaiveDateTime,
    pub end_utc: NaiveDateTime,
    pub credential: &'a Credential,
}

#[derive(Debug, Default)]
struct Msg {
    start: String,
    headers: Vec<(String, String)>,
    body: Vec<u8>,
}

impl Msg {
    fn header(&self, name: &str) -> Option<&str> {
        self.headers.iter().find(|(k, _)| k.eq_ignore_ascii_case(name)).map(|(_, v)| v.as_str())
    }
    fn set(&mut self, name: &str, value: &str) {
        self.remove(name);
        self.headers.push((name.to_string(), value.to_string()));
    }
    fn remove(&mut self, name: &str) {
        self.headers.retain(|(k, _)| !k.eq_ignore_ascii_case(name));
    }
    fn status(&self) -> u16 {
        self.start.split_whitespace().nth(1).and_then(|c| c.parse().ok()).unwrap_or(0)
    }
    fn write_to(&self, w: &mut impl Write) -> io::Result<()> {
        let mut out = Vec::with_capacity(256 + self.body.len());
        out.extend_from_slice(self.start.as_bytes());
        out.extend_from_slice(b"\r\n");
        for (k, v) in &self.headers {
            if k.eq_ignore_ascii_case("Content-Length") {
                continue;
            }
            out.extend_from_slice(format!("{k}: {v}\r\n").as_bytes());
        }
        if !self.body.is_empty() {
            out.extend_from_slice(format!("Content-Length: {}\r\n", self.body.len()).as_bytes());
        }
        out.extend_from_slice(b"\r\n");
        out.extend_from_slice(&self.body);
        w.write_all(&out)?;
        w.flush()
    }
}

fn read_msg(r: &mut impl BufRead) -> io::Result<Option<Msg>> {
    let mut msg = Msg::default();
    let mut total = 0;
    loop {
        let mut line = String::new();
        let n = r.read_line(&mut line)?;
        if n == 0 {
            return Ok(None);
        }
        total += n;
        if total > MAX_HEADER_BYTES {
            return Err(io::Error::new(io::ErrorKind::InvalidData, "RTSP header too large"));
        }
        let line = line.trim_end_matches(['\r', '\n']);
        if msg.start.is_empty() {
            if !line.is_empty() {
                msg.start = line.to_string();
            }
            continue;
        }
        if line.is_empty() {
            break;
        }
        if let Some((k, v)) = line.split_once(':') {
            msg.headers.push((k.trim().to_string(), v.trim().to_string()));
        }
    }
    let len: usize = msg.header("Content-Length").and_then(|v| v.parse().ok()).unwrap_or(0);
    if len > MAX_BODY_BYTES {
        return Err(io::Error::new(io::ErrorKind::InvalidData, "RTSP body too large"));
    }
    msg.body = vec![0; len];
    r.read_exact(&mut msg.body)?;
    Ok(Some(msg))
}

pub fn clock_range(start: NaiveDateTime, end: NaiveDateTime) -> String {
    format!("clock={}-{}", start.format("%Y%m%dT%H%M%SZ"), end.format("%Y%m%dT%H%M%SZ"))
}

/// Capture `[start, end)` of a recording into `out` (MP4, stream copy).
pub fn capture(tools: &Tools, replay: &Replay, out: &Path, timeout: Duration) -> Result<(), BridgeError> {
    let secs = (replay.end_utc - replay.start_utc).num_milliseconds() as f64 / 1000.0;
    if secs <= 0.0 {
        return Err(BridgeError::Usage("empty replay range".into()));
    }
    let host = replay.uri.host_str().ok_or_else(|| BridgeError::Protocol("replay uri has no host".into()))?.to_string();
    let port = replay.uri.port().unwrap_or(554);
    let mut camera_uri = replay.uri.clone();
    let _ = camera_uri.set_username("");
    let _ = camera_uri.set_password(None);
    let camera_uri = camera_uri.as_str().trim_end_matches('/').to_string();

    let listener = TcpListener::bind("127.0.0.1:0")?;
    listener.set_nonblocking(true)?;
    let local = format!("rtsp://127.0.0.1:{}{LOCAL_PATH}", listener.local_addr()?.port());

    let mut child = Command::new(&tools.ffmpeg)
        .args(["-nostdin", "-hide_banner", "-loglevel", "error", "-rtsp_transport", "tcp", "-timeout", "20000000", "-i"])
        .arg(&local)
        .args(["-map", "0:v:0", "-map", "0:a:0?", "-c", "copy", "-t"])
        .arg(format!("{secs:.3}"))
        .args(["-f", "mp4", "-y"])
        .arg(out)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| BridgeError::Usage(format!("cannot run {}: {e}", tools.ffmpeg.display())))?;
    let stderr_tail = collect_stderr(&mut child);
    let deadline = Instant::now() + timeout;

    let result = proxy(&listener, &mut child, &host, port, &camera_uri, &local, replay, deadline);
    let status = match &result {
        Ok(()) => wait_until(&mut child, deadline),
        Err(_) => {
            let _ = child.kill();
            child.wait().ok()
        }
    };
    result?;
    let tail = stderr_tail.lock().map(|s| s.clone()).unwrap_or_default();
    match status {
        Some(s) if s.success() => Ok(()),
        Some(s) => Err(BridgeError::Protocol(format!("ffmpeg exited with {s}: {}", tail.trim()))),
        None => Err(BridgeError::Unreachable(format!("replay timed out after {}s", timeout.as_secs()))),
    }
}

#[allow(clippy::too_many_arguments)]
fn proxy(
    listener: &TcpListener,
    child: &mut Child,
    host: &str,
    port: u16,
    camera_uri: &str,
    local: &str,
    replay: &Replay,
    deadline: Instant,
) -> Result<(), BridgeError> {
    // ffmpeg connects to us first.
    let accept_by = Instant::now() + HANDSHAKE_TIMEOUT;
    let ff = loop {
        match listener.accept() {
            Ok((s, _)) => break s,
            Err(e) if e.kind() == io::ErrorKind::WouldBlock => {
                if let Ok(Some(st)) = child.try_wait() {
                    return Err(BridgeError::Protocol(format!("ffmpeg exited before connecting ({st})")));
                }
                if Instant::now() > accept_by {
                    return Err(BridgeError::Protocol("ffmpeg never connected to the replay proxy".into()));
                }
                std::thread::sleep(Duration::from_millis(20));
            }
            Err(e) => return Err(e.into()),
        }
    };
    ff.set_nonblocking(false)?;
    let addr = (host, port)
        .to_socket_addrs()
        .map_err(|e| BridgeError::Unreachable(format!("{host}:{port}: {e}")))?
        .next()
        .ok_or_else(|| BridgeError::Unreachable(format!("{host}:{port}: no address")))?;
    let cam = TcpStream::connect_timeout(&addr, Duration::from_secs(5))
        .map_err(|e| BridgeError::Unreachable(format!("rtsp {host}:{port}: {e}")))?;
    for s in [&ff, &cam] {
        s.set_read_timeout(Some(HANDSHAKE_TIMEOUT))?;
        s.set_nodelay(true)?;
    }
    let mut ff_r = BufReader::new(ff.try_clone()?);
    let mut ff_w = ff.try_clone()?;
    let mut cam_r = BufReader::new(cam.try_clone()?);
    let mut cam_w = cam.try_clone()?;
    let mut digest: Option<DigestSession> = None;
    let cred = replay.credential;
    let range = clock_range(replay.start_utc, replay.end_utc);
    let rtsp_err = |e: io::Error| BridgeError::Unreachable(format!("rtsp: {e}"));

    loop {
        let Some(mut rq) = read_msg(&mut ff_r).map_err(rtsp_err)? else {
            return Err(BridgeError::Protocol("ffmpeg closed the replay session before PLAY".into()));
        };
        let mut parts = rq.start.splitn(3, ' ');
        let method = parts.next().unwrap_or("").to_ascii_uppercase();
        let target = parts.next().unwrap_or("").to_string();
        let version = parts.next().unwrap_or("RTSP/1.0").to_string();
        let target = match target.strip_prefix(local) {
            Some(rest) => format!("{camera_uri}{rest}"),
            None => target,
        };
        rq.start = format!("{method} {target} {version}");
        rq.remove("Authorization");
        if method == "SETUP" || method == "PLAY" {
            rq.set("Require", "onvif-replay");
        }
        if method == "PLAY" {
            rq.set("Range", &range);
            rq.set("Rate-Control", "no");
        }

        let mut retried = false;
        let resp = loop {
            if let Some(d) = digest.as_mut() {
                rq.set("Authorization", &d.authorize(&method, &target, &cred.username, cred.password.expose()));
            }
            rq.write_to(&mut cam_w).map_err(rtsp_err)?;
            let resp = read_msg(&mut cam_r)
                .map_err(rtsp_err)?
                .ok_or_else(|| BridgeError::Unreachable(format!("camera closed the RTSP session during {method}")))?;
            if resp.status() == 401 {
                let c = resp.header("WWW-Authenticate").and_then(Challenge::parse);
                match c {
                    Some(c) if !retried && (digest.is_none() || c.stale) => {
                        digest = Some(DigestSession::new(c));
                        retried = true;
                        continue;
                    }
                    _ => return Err(BridgeError::AuthRejected { status: 401 }),
                }
            }
            if resp.status() == 403 {
                return Err(BridgeError::AuthRejected { status: 403 });
            }
            break resp;
        };
        let code = resp.status();
        if code >= 300 {
            let reason = resp.start.splitn(3, ' ').nth(2).unwrap_or("").to_string();
            return Err(match code {
                551 => BridgeError::Unsupported(format!("{method}: camera does not support onvif-replay (RTSP 551)")),
                457 => BridgeError::Protocol(format!("{method}: range {range} not available (RTSP 457)")),
                _ => BridgeError::Protocol(format!("{method}: RTSP {code} {reason}").trim().to_string()),
            });
        }
        let mut resp = resp;
        resp.remove("WWW-Authenticate");
        resp.write_to(&mut ff_w).map_err(rtsp_err)?;
        if method == "PLAY" {
            break;
        }
        if Instant::now() > deadline {
            return Err(BridgeError::Unreachable("replay handshake timed out".into()));
        }
    }

    // Media phase: relay bytes both ways until ffmpeg finishes.
    let remaining = deadline.saturating_duration_since(Instant::now()).max(Duration::from_secs(1));
    ff.set_read_timeout(Some(remaining))?;
    cam.set_read_timeout(Some(remaining))?;
    let down = std::thread::spawn(move || {
        let _ = io::copy(&mut cam_r, &mut ff_w);
        let _ = ff_w.shutdown(Shutdown::Write);
    });
    let up = std::thread::spawn(move || {
        let _ = io::copy(&mut ff_r, &mut cam_w);
        let _ = cam_w.shutdown(Shutdown::Write);
    });
    // The caller waits for ffmpeg; tear the sockets down once it is gone.
    let _ = wait_until_peek(child, deadline);
    let _ = ff.shutdown(Shutdown::Both);
    let _ = cam.shutdown(Shutdown::Both);
    let _ = down.join();
    let _ = up.join();
    Ok(())
}

fn wait_until_peek(child: &mut Child, deadline: Instant) -> Option<()> {
    loop {
        if let Ok(Some(_)) = child.try_wait() {
            return Some(());
        }
        if Instant::now() > deadline {
            let _ = child.kill();
            return None;
        }
        std::thread::sleep(Duration::from_millis(25));
    }
}

fn wait_until(child: &mut Child, deadline: Instant) -> Option<std::process::ExitStatus> {
    loop {
        if let Ok(Some(s)) = child.try_wait() {
            return Some(s);
        }
        if Instant::now() > deadline {
            let _ = child.kill();
            let _ = child.wait();
            return None;
        }
        std::thread::sleep(Duration::from_millis(25));
    }
}

fn collect_stderr(child: &mut Child) -> Arc<Mutex<String>> {
    let tail = Arc::new(Mutex::new(String::new()));
    if let Some(mut err) = child.stderr.take() {
        let t = tail.clone();
        std::thread::spawn(move || {
            let mut buf = [0u8; 4096];
            while let Ok(n) = err.read(&mut buf) {
                if n == 0 {
                    break;
                }
                let mut s = t.lock().unwrap();
                s.push_str(&String::from_utf8_lossy(&buf[..n]));
                if s.len() > 8192 {
                    let cut = s.len() - 4096;
                    let cut = (cut..s.len()).find(|i| s.is_char_boundary(*i)).unwrap_or(s.len());
                    s.drain(..cut);
                }
            }
        });
    }
    tail
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn clock_range_is_onvif_absolute_utc() {
        let s = NaiveDateTime::parse_from_str("2026-10-30T14:28:00", "%Y-%m-%dT%H:%M:%S").unwrap();
        let e = NaiveDateTime::parse_from_str("2026-10-30T14:30:00", "%Y-%m-%dT%H:%M:%S").unwrap();
        assert_eq!(clock_range(s, e), "clock=20261030T142800Z-20261030T143000Z");
    }

    #[test]
    fn message_roundtrip() {
        let raw = b"RTSP/1.0 200 OK\r\nCSeq: 2\r\nContent-Length: 5\r\n\r\nv=0\r\n$\x00";
        let mut r = BufReader::new(&raw[..]);
        let m = read_msg(&mut r).unwrap().unwrap();
        assert_eq!(m.status(), 200);
        assert_eq!(m.body, b"v=0\r\n");
        let mut rest = Vec::new();
        r.read_to_end(&mut rest).unwrap();
        assert_eq!(rest, b"$\x00", "interleaved bytes after the response stay buffered");
    }
}
