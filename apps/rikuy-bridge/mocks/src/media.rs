//! Real, decodable media for the mock camera: a short HEVC + AAC clip and a
//! JPEG, generated once with ffmpeg (synthetic test pattern, no footage of
//! people), plus the RTP packetizers the mock RTSP server streams them with.
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::OnceLock;

pub const FPS: u32 = 15;
pub const CLIP_SECS: u32 = 10;
const RTP_MAX_PAYLOAD: usize = 1200;

pub struct Fixture {
    pub vps: Vec<u8>,
    pub sps: Vec<u8>,
    pub pps: Vec<u8>,
    /// Access units, each a list of NAL units without start codes.
    pub aus: Vec<Vec<Vec<u8>>>,
    /// Raw AAC access units (ADTS header stripped).
    pub audio: Vec<Vec<u8>>,
    pub sample_rate: u32,
    pub audio_channels: u8,
    /// AudioSpecificConfig.
    pub asc: u16,
    pub jpeg: Vec<u8>,
}

pub fn ffmpeg() -> PathBuf {
    std::env::var_os("RIKUY_FFMPEG").map(PathBuf::from).unwrap_or_else(|| "ffmpeg".into())
}

fn run(args: &[&str]) {
    let out = Command::new(ffmpeg()).args(["-nostdin", "-hide_banner", "-loglevel", "error", "-y"]).args(args).output().expect("ffmpeg is required by the mock camera");
    assert!(out.status.success(), "ffmpeg {:?}: {}", args, String::from_utf8_lossy(&out.stderr));
}

fn generate(dir: &Path) {
    std::fs::create_dir_all(dir).unwrap();
    let p = |n: &str| dir.join(n).to_string_lossy().to_string();
    let dur = CLIP_SECS.to_string();
    let v = format!("testsrc2=size=320x180:rate={FPS}:duration={dur}");
    run(&[
        "-f", "lavfi", "-i", &v, "-c:v", "libx265", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-x265-params", &format!("keyint={FPS}:min-keyint={FPS}:bframes=0:repeat-headers=1:log-level=error"),
        "-f", "hevc", &p("video.hevc"),
    ]);
    run(&[
        "-f", "lavfi", "-i", &format!("sine=frequency=440:sample_rate=16000:duration={dur}"),
        "-c:a", "aac", "-ac", "1", "-b:a", "32k", "-f", "adts", &p("audio.adts"),
    ]);
    run(&["-f", "lavfi", "-i", "testsrc2=size=640x360:rate=1", "-frames:v", "1", "-q:v", "4", &p("snapshot.jpg")]);
}

/// Generated once per machine (cached in the temp dir) and once per process.
pub fn fixture() -> &'static Fixture {
    static F: OnceLock<Fixture> = OnceLock::new();
    F.get_or_init(|| {
        let dir = std::env::temp_dir().join("rikuy-mock-onvif-fixture-v1");
        if !dir.join("snapshot.jpg").exists() {
            let tmp = std::env::temp_dir().join(format!("rikuy-mock-onvif-fixture-{}-{:?}", std::process::id(), std::thread::current().id()));
            generate(&tmp);
            if std::fs::rename(&tmp, &dir).is_err() {
                let _ = std::fs::remove_dir_all(&tmp);
            }
        }
        load(&dir)
    })
}

fn load(dir: &Path) -> Fixture {
    let video = std::fs::read(dir.join("video.hevc")).unwrap();
    let adts = std::fs::read(dir.join("audio.adts")).unwrap();
    let jpeg = std::fs::read(dir.join("snapshot.jpg")).unwrap();
    let nals = split_annex_b(&video);
    let (mut vps, mut sps, mut pps) = (vec![], vec![], vec![]);
    let mut aus: Vec<Vec<Vec<u8>>> = vec![];
    let mut cur: Vec<Vec<u8>> = vec![];
    let mut cur_has_vcl = false;
    for n in nals {
        if n.len() < 3 {
            continue;
        }
        let t = (n[0] >> 1) & 0x3f;
        match t {
            32 if vps.is_empty() => vps = n.clone(),
            33 if sps.is_empty() => sps = n.clone(),
            34 if pps.is_empty() => pps = n.clone(),
            _ => {}
        }
        let vcl = t < 32;
        let first_slice = vcl && n[2] & 0x80 != 0;
        let starts_au = (vcl && first_slice) || matches!(t, 32..=35 | 39);
        if starts_au && cur_has_vcl {
            aus.push(std::mem::take(&mut cur));
            cur_has_vcl = false;
        }
        cur_has_vcl |= vcl;
        cur.push(n);
    }
    if !cur.is_empty() {
        aus.push(cur);
    }
    assert_eq!(aus.len() as u32, FPS * CLIP_SECS, "unexpected access unit count in the HEVC fixture");

    let mut audio = vec![];
    let mut asc = 0u16;
    let (mut sample_rate, mut audio_channels) = (16000, 1);
    let mut i = 0;
    while i + 7 <= adts.len() {
        let h = &adts[i..];
        assert!(h[0] == 0xFF && h[1] & 0xF0 == 0xF0, "bad ADTS sync");
        let protection_absent = h[1] & 1 == 1;
        let len = (((h[3] & 0x03) as usize) << 11) | ((h[4] as usize) << 3) | ((h[5] as usize) >> 5);
        let hdr = if protection_absent { 7 } else { 9 };
        let profile = ((h[2] >> 6) & 0x3) as u16 + 1;
        let freq = ((h[2] >> 2) & 0xF) as u16;
        let ch = (((h[2] & 1) << 2) | (h[3] >> 6)) as u16;
        asc = (profile << 11) | (freq << 7) | (ch << 3);
        sample_rate = [96000, 88200, 64000, 48000, 44100, 32000, 24000, 22050, 16000, 12000, 11025, 8000, 7350][freq as usize];
        audio_channels = ch as u8;
        audio.push(adts[i + hdr..i + len].to_vec());
        i += len;
    }
    Fixture { vps, sps, pps, aus, audio, sample_rate, audio_channels, asc, jpeg }
}

pub fn split_annex_b(b: &[u8]) -> Vec<Vec<u8>> {
    let mut starts = vec![];
    let mut i = 0;
    while i + 3 <= b.len() {
        if b[i] == 0 && b[i + 1] == 0 && b[i + 2] == 1 {
            starts.push(i + 3);
            i += 3;
        } else {
            i += 1;
        }
    }
    let mut out = vec![];
    for (k, &s) in starts.iter().enumerate() {
        let mut e = if k + 1 < starts.len() { starts[k + 1] - 3 } else { b.len() };
        while e > s && b[e - 1] == 0 {
            e -= 1;
        }
        out.push(b[s..e].to_vec());
    }
    out
}

pub fn b64(b: &[u8]) -> String {
    use base64::Engine;
    base64::engine::general_purpose::STANDARD.encode(b)
}

impl Fixture {
    pub fn sdp(&self, base: &str) -> String {
        format!(
            concat!(
                "v=0\r\no=- 1 1 IN IP4 127.0.0.1\r\ns=Rikuy mock ONVIF replay\r\nt=0 0\r\na=control:{base}\r\n",
                "m=video 0 RTP/AVP 96\r\na=control:trackID=0\r\na=rtpmap:96 H265/90000\r\n",
                "a=fmtp:96 sprop-vps={};sprop-sps={};sprop-pps={}\r\n",
                "m=audio 0 RTP/AVP 97\r\na=control:trackID=1\r\na=rtpmap:97 MPEG4-GENERIC/{}/{}\r\n",
                "a=fmtp:97 streamtype=5;profile-level-id=15;mode=AAC-hbr;sizelength=13;indexlength=3;indexdeltalength=3;config={:04x}\r\n"
            ),
            b64(&self.vps),
            b64(&self.sps),
            b64(&self.pps),
            self.sample_rate,
            self.audio_channels,
            self.asc,
            base = base
        )
    }
}

fn rtp(pt: u8, marker: bool, seq: u16, ts: u32, ssrc: u32, payload: &[u8]) -> Vec<u8> {
    let mut p = Vec::with_capacity(12 + payload.len());
    p.push(0x80);
    p.push(pt | if marker { 0x80 } else { 0 });
    p.extend_from_slice(&seq.to_be_bytes());
    p.extend_from_slice(&ts.to_be_bytes());
    p.extend_from_slice(&ssrc.to_be_bytes());
    p.extend_from_slice(payload);
    p
}

fn interleaved(channel: u8, packet: &[u8]) -> Vec<u8> {
    let mut f = Vec::with_capacity(4 + packet.len());
    f.push(b'$');
    f.push(channel);
    f.extend_from_slice(&(packet.len() as u16).to_be_bytes());
    f.extend_from_slice(packet);
    f
}

/// Interleaved RTP frames for `secs` seconds of media (the clip loops), in
/// presentation order. RFC 7798 (H.265) and RFC 3640 (AAC-hbr).
pub fn stream_frames(f: &Fixture, secs: f64, video_ch: u8, audio_ch: Option<u8>, mut emit: impl FnMut(&[u8]) -> bool) {
    let n_video = (secs * FPS as f64).round() as usize;
    let samples_per_frame = 1024.0;
    let n_audio = (secs * f.sample_rate as f64 / samples_per_frame).floor() as usize;
    let (mut vi, mut ai) = (0usize, 0usize);
    let (mut vseq, mut aseq) = (1000u16, 5000u16);
    while vi < n_video || (audio_ch.is_some() && ai < n_audio) {
        let vt = vi as f64 / FPS as f64;
        let at = ai as f64 * samples_per_frame / f.sample_rate as f64;
        let take_video = vi < n_video && (audio_ch.is_none() || ai >= n_audio || vt <= at);
        if take_video {
            let au = &f.aus[vi % f.aus.len()];
            let ts = (vi as u32).wrapping_mul(90000 / FPS);
            for (k, nal) in au.iter().enumerate() {
                let last_nal = k + 1 == au.len();
                if nal.len() <= RTP_MAX_PAYLOAD {
                    vseq = vseq.wrapping_add(1);
                    if !emit(&interleaved(video_ch, &rtp(96, last_nal, vseq, ts, 0x1111, nal))) {
                        return;
                    }
                } else {
                    let t = (nal[0] >> 1) & 0x3f;
                    let ph = [(nal[0] & 0x81) | (49 << 1), nal[1]];
                    let body = &nal[2..];
                    let chunks: Vec<&[u8]> = body.chunks(RTP_MAX_PAYLOAD).collect();
                    for (j, c) in chunks.iter().enumerate() {
                        let s = j == 0;
                        let e = j + 1 == chunks.len();
                        let mut pl = vec![ph[0], ph[1], t | if s { 0x80 } else { 0 } | if e { 0x40 } else { 0 }];
                        pl.extend_from_slice(c);
                        vseq = vseq.wrapping_add(1);
                        if !emit(&interleaved(video_ch, &rtp(96, last_nal && e, vseq, ts, 0x1111, &pl))) {
                            return;
                        }
                    }
                }
            }
            vi += 1;
        } else if let Some(ach) = audio_ch {
            let frame = &f.audio[ai % f.audio.len()];
            let mut pl = Vec::with_capacity(4 + frame.len());
            pl.extend_from_slice(&16u16.to_be_bytes());
            pl.extend_from_slice(&((frame.len() as u16) << 3).to_be_bytes());
            pl.extend_from_slice(frame);
            aseq = aseq.wrapping_add(1);
            let ts = (ai as u32).wrapping_mul(1024);
            if !emit(&interleaved(ach, &rtp(97, true, aseq, ts, 0x2222, &pl))) {
                return;
            }
            ai += 1;
        }
    }
}
