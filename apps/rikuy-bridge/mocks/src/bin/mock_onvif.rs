//! Run the mock Ezviz ONVIF camera standalone: `mock-onvif [http_addr] [rtsp_addr]`.
use rikuy_bridge_mocks::onvif::{MockOnvif, OnvifConfig};

fn main() {
    let mut args = std::env::args().skip(1);
    let http = args.next().unwrap_or_else(|| "127.0.0.1:8081".into());
    let rtsp = args.next().unwrap_or_else(|| "127.0.0.1:8554".into());
    let cfg = OnvifConfig::ezviz_two_channel();
    eprintln!("mock-onvif: user={} password={} tz={:?} skew={}s", cfg.username, cfg.password, cfg.tz, cfg.clock_skew_secs);
    let m = MockOnvif::start_on(&http, &rtsp, cfg);
    eprintln!("mock-onvif listening on {} (rtsp port {})", m.base_url, m.rtsp_port);
    loop {
        std::thread::park();
    }
}
