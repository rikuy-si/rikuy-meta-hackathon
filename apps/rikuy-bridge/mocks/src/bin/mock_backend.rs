//! Run the mock backend standalone: `mock-backend [addr] [token] [jobs.json]`.
//! jobs.json is a JSON array of jobs enqueued at startup. Reports are printed.
use rikuy_bridge_mocks::backend::MockBackend;

fn main() {
    let mut args = std::env::args().skip(1);
    let addr = args.next().unwrap_or_else(|| "127.0.0.1:8090".into());
    let token = args.next().unwrap_or_else(|| "dev-bridge-token".into());
    let b = MockBackend::start_on(&addr, &token);
    if let Some(path) = args.next() {
        let jobs: Vec<serde_json::Value> =
            serde_json::from_str(&std::fs::read_to_string(&path).expect("read jobs file")).expect("jobs json");
        for j in jobs {
            b.enqueue(j);
        }
    }
    eprintln!("mock-backend listening on {}", b.base_url);
    let mut seen = 0;
    loop {
        std::thread::sleep(std::time::Duration::from_millis(500));
        let reports = b.reports();
        for r in &reports[seen..] {
            println!("{}", serde_json::to_string(r).unwrap());
        }
        seen = reports.len();
    }
}
