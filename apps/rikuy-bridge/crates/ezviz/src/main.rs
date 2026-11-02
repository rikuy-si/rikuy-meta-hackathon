use std::io::Read;
use std::path::PathBuf;
use std::process::ExitCode as ProcExit;
use std::time::Duration;

use chrono::NaiveDateTime;
use clap::{Args, Parser, Subcommand};
use rikuy_bridge_common::backend::BackendClient;
use rikuy_bridge_common::daemon::{self, DaemonConfig};
use rikuy_bridge_common::{BridgeError, Credential, Secret};
use rikuy_bridge_ezviz::exec::{Options, Session};
use rikuy_bridge_ezviz::rtsp::Tools;
use rikuy_bridge_ezviz::EzvizConnector;

/// rikuy-bridge for Ezviz cameras over ONVIF (Profile T live, Profile G
/// recordings).
///
/// Runs on the customer's network next to the cameras. One-shot commands read
/// the device password from RIKUY_DEVICE_PASSWORD or stdin, never from argv.
/// Times are device-local wall-clock. Recordings need ffmpeg and ffprobe
/// (RIKUY_FFMPEG / RIKUY_FFPROBE override the paths).
/// Exit codes: 0 ok, 64 usage, 69 device unreachable, 76 protocol error,
/// 77 credential rejected (never retried: the device may lock the account).
#[derive(Parser)]
#[command(name = "rikuy-bridge-ezviz", version)]
struct Cli {
    #[command(subcommand)]
    cmd: Cmd,
}

#[derive(Args, Clone)]
struct DeviceArgs {
    /// ONVIF address as seen from this host: http://10.0.0.30 (device service
    /// at /onvif/device_service) or the full device service URL.
    #[arg(long)]
    device: String,
    /// ONVIF account name.
    #[arg(long, env = "RIKUY_DEVICE_USER", default_value = "admin")]
    user: String,
    /// Read the device password from stdin instead of RIKUY_DEVICE_PASSWORD.
    #[arg(long)]
    password_stdin: bool,
}

#[derive(Args, Clone)]
struct MediaArgs {
    /// Maximum length of one recording file, seconds.
    #[arg(long, default_value_t = 900)]
    chunk_secs: i64,
}

#[derive(Subcommand)]
enum Cmd {
    /// Device identity, clock, time zone and the ONVIF services it offers.
    DeviceInfo {
        #[command(flatten)]
        dev: DeviceArgs,
    },
    /// List cameras (one per video source) with their recordings.
    ListCameras {
        #[command(flatten)]
        dev: DeviceArgs,
    },
    /// Save a live JPEG from one camera.
    Screenshot {
        #[command(flatten)]
        dev: DeviceArgs,
        /// Camera number (1-based).
        #[arg(long)]
        channel: u32,
        #[arg(long)]
        out: PathBuf,
    },
    /// List recorded segments in a device-local window as JSON.
    Search {
        #[command(flatten)]
        dev: DeviceArgs,
        #[arg(long, value_parser = parse_local)]
        from: NaiveDateTime,
        #[arg(long, value_parser = parse_local)]
        to: NaiveDateTime,
        /// Camera number. Repeatable. Default: all cameras.
        #[arg(long = "track")]
        tracks: Vec<u32>,
    },
    /// Download every recording in a device-local window as MP4 files.
    Download {
        #[command(flatten)]
        dev: DeviceArgs,
        #[command(flatten)]
        media: MediaArgs,
        #[arg(long, value_parser = parse_local)]
        from: NaiveDateTime,
        #[arg(long, value_parser = parse_local)]
        to: NaiveDateTime,
        #[arg(long = "track")]
        tracks: Vec<u32>,
        #[arg(long)]
        out: PathBuf,
    },
    /// Poll the Rikuy backend for Ezviz jobs and report results.
    Daemon {
        #[arg(long, env = "RIKUY_BACKEND_URL")]
        backend: String,
        #[arg(long, env = "RIKUY_BRIDGE_TOKEN_FILE")]
        token_file: PathBuf,
        #[arg(long, default_value = "spool")]
        spool: PathBuf,
        #[arg(long, default_value = "rikuy-bridge-ezviz")]
        bridge_id: String,
        #[arg(long, default_value_t = 5000)]
        poll_interval_ms: u64,
        #[arg(long, default_value_t = 30000)]
        unreachable_backoff_ms: u64,
        #[arg(long)]
        exit_when_idle: bool,
        /// Presigned upload URLs requested per batch.
        #[arg(long, default_value_t = 16)]
        upload_batch: usize,
        #[command(flatten)]
        media: MediaArgs,
    },
}

fn parse_local(s: &str) -> Result<NaiveDateTime, String> {
    NaiveDateTime::parse_from_str(s.trim_end_matches('Z'), "%Y-%m-%dT%H:%M:%S").map_err(|e| e.to_string())
}

fn credential(dev: &DeviceArgs) -> Result<Credential, BridgeError> {
    let password = if dev.password_stdin {
        let mut s = String::new();
        std::io::stdin().read_to_string(&mut s)?;
        s.trim_end_matches(['\r', '\n']).to_string()
    } else {
        std::env::var("RIKUY_DEVICE_PASSWORD")
            .map_err(|_| BridgeError::Usage("set RIKUY_DEVICE_PASSWORD or pass --password-stdin".into()))?
    };
    Ok(Credential { username: dev.user.clone(), password: Secret::new(password) })
}

fn session(dev: &DeviceArgs) -> Result<Session, BridgeError> {
    Session::open(&dev.device, credential(dev)?)
}

fn options(media: &MediaArgs) -> Options {
    Options { tools: Tools::default(), chunk_secs: media.chunk_secs, ..Default::default() }
}

fn print_json<T: serde::Serialize>(v: &T) {
    println!("{}", serde_json::to_string_pretty(v).expect("serializable"));
}

fn run(cli: Cli) -> Result<(), BridgeError> {
    match cli.cmd {
        Cmd::DeviceInfo { dev } => {
            let s = session(&dev)?;
            let c = &s.dev.clock;
            print_json(&serde_json::json!({
                "info": s.dev.info,
                "clock": {
                    "timezone": c.tz_string,
                    "daylight_savings": c.daylight_savings,
                    "tz_rules_parsed": c.rules.is_some(),
                    "tz_rules_consistent": c.rules_consistent(),
                    "observed_utc_offset_secs": c.observed_offset,
                    "utc_offset_secs": c.offset_now(),
                    "skew_secs": c.skew_secs,
                    "device_utc": c.device_utc_at_sync,
                },
                "profile_t_media2": s.dev.has_service(rikuy_bridge_ezviz::onvif::NS_MEDIA2),
                "profile_g_search": s.dev.has_service(rikuy_bridge_ezviz::onvif::NS_SEARCH),
                "profile_g_replay": s.dev.has_service(rikuy_bridge_ezviz::onvif::NS_REPLAY),
            }));
        }
        Cmd::ListCameras { dev } => print_json(&session(&dev)?.cameras()?),
        Cmd::Screenshot { dev, channel, out } => print_json(&session(&dev)?.snapshot(channel, &out)?),
        Cmd::Search { dev, from, to, tracks } => print_json(&session(&dev)?.search(from, to, &tracks)?),
        Cmd::Download { dev, media, from, to, tracks, out } => {
            let s = session(&dev)?.download_range(&options(&media), from, to, &tracks, &out)?;
            print_json(&serde_json::json!({
                "found": s.found,
                "downloaded": s.artifacts.len() - s.skipped,
                "skipped_existing": s.skipped,
                "bytes": s.artifacts.iter().map(|a| a.bytes).sum::<u64>(),
                "files": s.artifacts.iter().map(|a| &a.name).collect::<Vec<_>>(),
                "error": s.error.as_ref().map(|e| e.to_string()),
            }));
            if let Some(e) = s.error {
                return Err(e);
            }
        }
        Cmd::Daemon { backend, token_file, spool, bridge_id, poll_interval_ms, unreachable_backoff_ms, exit_when_idle, upload_batch, media } => {
            let token = std::fs::read_to_string(&token_file)
                .map_err(|e| BridgeError::Usage(format!("token file {}: {e}", token_file.display())))?;
            let backend = BackendClient::new(&backend, Secret::new(token.trim()), &bridge_id)?;
            let cfg = DaemonConfig {
                spool,
                poll_interval: Duration::from_millis(poll_interval_ms),
                unreachable_backoff: Duration::from_millis(unreachable_backoff_ms),
                exit_when_idle,
                upload_batch,
            };
            let mut connector = EzvizConnector { opts: options(&media) };
            let stats = daemon::run(&mut connector, &backend, &cfg)?;
            daemon::log(&format!("idle: {} jobs, {} succeeded, {} not", stats.jobs, stats.succeeded, stats.failed));
        }
    }
    Ok(())
}

fn main() -> ProcExit {
    match run(Cli::parse()) {
        Ok(()) => ProcExit::SUCCESS,
        Err(e) => {
            eprintln!("rikuy-bridge-ezviz: error[{}]: {e}", e.code());
            ProcExit::from(e.exit_code() as u8)
        }
    }
}
