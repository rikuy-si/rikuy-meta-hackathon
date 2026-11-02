use std::io::Read;
use std::path::PathBuf;
use std::process::ExitCode as ProcExit;
use std::time::Duration;

use chrono::NaiveDateTime;
use clap::{Args, Parser, Subcommand};
use rikuy_bridge_common::{BridgeError, Credential, Secret};
use rikuy_bridge_common::backend::BackendClient;
use rikuy_bridge_common::daemon::{self, DaemonConfig};
use rikuy_bridge_hikvision::connector::HikvisionConnector;
use rikuy_bridge_hikvision::exec;
use rikuy_bridge_hikvision::isapi::{IsapiClient, Stream};

/// rikuy-bridge for Hikvision/HiLook DVRs and NVRs.
///
/// Runs on the customer's network next to the recorder. One-shot commands read
/// the device password from RIKUY_DEVICE_PASSWORD or stdin, never from argv.
/// Exit codes: 0 ok, 64 usage, 69 device unreachable, 76 protocol error,
/// 77 credential rejected (never retried: the device may lock the account).
#[derive(Parser)]
#[command(name = "rikuy-bridge-hikvision", version)]
struct Cli {
    #[command(subcommand)]
    cmd: Cmd,
}

#[derive(Args, Clone)]
struct DeviceArgs {
    /// Device base URL as seen from this host, e.g. http://10.0.0.20
    #[arg(long)]
    device: String,
    /// Device account name.
    #[arg(long, env = "RIKUY_DEVICE_USER", default_value = "admin")]
    user: String,
    /// Read the device password from stdin instead of RIKUY_DEVICE_PASSWORD.
    #[arg(long)]
    password_stdin: bool,
}

#[derive(Subcommand)]
enum Cmd {
    /// List recording tracks (cameras) on the device.
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
        /// Use the sub stream instead of the main stream.
        #[arg(long)]
        substream: bool,
        #[arg(long)]
        out: PathBuf,
    },
    /// List recordings in a local-time window as JSON.
    Search {
        #[command(flatten)]
        dev: DeviceArgs,
        #[arg(long, value_parser = parse_local)]
        from: NaiveDateTime,
        #[arg(long, value_parser = parse_local)]
        to: NaiveDateTime,
        /// Track id (101, 201, ...). Repeatable. Default: all enabled tracks.
        #[arg(long = "track")]
        tracks: Vec<u32>,
    },
    /// Download every recording in a local-time window into a directory.
    Download {
        #[command(flatten)]
        dev: DeviceArgs,
        #[arg(long, value_parser = parse_local)]
        from: NaiveDateTime,
        #[arg(long, value_parser = parse_local)]
        to: NaiveDateTime,
        #[arg(long = "track")]
        tracks: Vec<u32>,
        #[arg(long)]
        out: PathBuf,
    },
    /// Run as the customer-site agent: poll the Rikuy backend for jobs,
    /// execute them against the devices on this network, report results.
    /// Device credentials arrive per job and are held in memory only.
    Daemon {
        /// Rikuy backend base URL.
        #[arg(long, env = "RIKUY_BACKEND_URL")]
        backend: String,
        /// File holding this bridge's enrollment token (not a device secret).
        #[arg(long, env = "RIKUY_BRIDGE_TOKEN_FILE")]
        token_file: PathBuf,
        /// Working directory for job outputs (recordings stay here).
        #[arg(long, default_value = "spool")]
        spool: PathBuf,
        #[arg(long, default_value = "rikuy-bridge-hikvision")]
        bridge_id: String,
        #[arg(long, default_value_t = 5000)]
        poll_interval_ms: u64,
        /// Pause after a job fails because the device route is down.
        #[arg(long, default_value_t = 30000)]
        unreachable_backoff_ms: u64,
        /// Exit when the queue is empty (tests, cron-style runs).
        #[arg(long)]
        exit_when_idle: bool,
        /// Presigned upload URLs requested per batch (keeps them from expiring
        /// while earlier recordings upload).
        #[arg(long, default_value_t = 16)]
        upload_batch: usize,
    },
}

/// Local wall-clock time on the device: 2026-10-29T05:00:00 (a trailing Z is
/// accepted and ignored, matching how the DVR writes it).
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

fn client(dev: &DeviceArgs) -> Result<IsapiClient, BridgeError> {
    IsapiClient::new(&dev.device, credential(dev)?)
}

fn print_json<T: serde::Serialize>(v: &T) {
    println!("{}", serde_json::to_string_pretty(v).expect("serializable"));
}

fn run(cli: Cli) -> Result<(), BridgeError> {
    match cli.cmd {
        Cmd::ListCameras { dev } => print_json(&client(&dev)?.tracks()?),
        Cmd::Screenshot { dev, channel, substream, out } => {
            let stream = if substream { Stream::Sub } else { Stream::Main };
            print_json(&exec::snapshot(&mut client(&dev)?, channel, stream, &out)?);
        }
        Cmd::Search { dev, from, to, tracks } => print_json(&client(&dev)?.search(from, to, &tracks)?),
        Cmd::Download { dev, from, to, tracks, out } => {
            let s = exec::download_range(&mut client(&dev)?, from, to, &tracks, &out)?;
            print_json(&serde_json::json!({
                "found": s.found,
                "downloaded": s.artifacts.len() - s.skipped,
                "skipped_existing": s.skipped,
                "bytes": s.artifacts.iter().map(|a| a.bytes).sum::<u64>(),
                "error": s.error.as_ref().map(|e| e.to_string()),
            }));
            if let Some(e) = s.error {
                return Err(e);
            }
        }
        Cmd::Daemon { backend, token_file, spool, bridge_id, poll_interval_ms, unreachable_backoff_ms, exit_when_idle, upload_batch } => {
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
            let stats = daemon::run(&mut HikvisionConnector, &backend, &cfg)?;
            daemon::log(&format!("idle: {} jobs, {} succeeded, {} not", stats.jobs, stats.succeeded, stats.failed));
        }
    }
    Ok(())
}

fn main() -> ProcExit {
    let cli = Cli::parse();
    match run(cli) {
        Ok(()) => ProcExit::SUCCESS,
        Err(e) => {
            eprintln!("rikuy-bridge-hikvision: error[{}]: {e}", e.code());
            ProcExit::from(e.exit_code() as u8)
        }
    }
}

