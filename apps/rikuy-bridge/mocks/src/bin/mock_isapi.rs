//! Run the mock DVR standalone: `mock-isapi [addr] [clips_per_track]`.
use rikuy_bridge_mocks::isapi::{IsapiConfig, MockIsapi};

fn main() {
    let mut args = std::env::args().skip(1);
    let addr = args.next().unwrap_or_else(|| "127.0.0.1:8080".into());
    let clips: usize = args.next().and_then(|s| s.parse().ok()).unwrap_or(96);
    let cfg = IsapiConfig::eight_channel_dvr(clips);
    eprintln!("mock-isapi: user={} password={} clips={}", cfg.username, cfg.password, cfg.clips.len());
    let m = MockIsapi::start_on(&addr, cfg);
    eprintln!("mock-isapi listening on {}", m.base_url);
    loop {
        std::thread::park();
    }
}
