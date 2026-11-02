use std::path::PathBuf;
use std::process::ExitCode as ProcExit;
use std::time::Duration;

use clap::{Parser, Subcommand};
use rikuy_bridge_common::backend::BackendClient;
use rikuy_bridge_common::daemon::{self, DaemonConfig};
use rikuy_bridge_common::{BridgeError, Secret};
use rikuy_bridge_ezviz::EzvizConnector;

/// rikuy-bridge for Ezviz cameras (scaffold: jobs are accepted and answered
/// `unsupported` until the protocol client lands).
#[derive(Parser)]
#[command(name = "rikuy-bridge-ezviz", version)]
struct Cli {
    #[command(subcommand)]
    cmd: Cmd,
}

#[derive(Subcommand)]
enum Cmd {
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
        /// Presigned upload URLs requested per batch (keeps them from expiring
        /// while earlier recordings upload).
        #[arg(long, default_value_t = 16)]
        upload_batch: usize,
    },
}

fn run(cli: Cli) -> Result<(), BridgeError> {
    match cli.cmd {
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
            daemon::run(&mut EzvizConnector, &backend, &cfg)?;
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
