use tiny_http::{Header, Request, Response};

pub fn header(rq: &Request, name: &str) -> Option<String> {
    rq.headers()
        .iter()
        .find(|h| h.field.as_str().as_str().eq_ignore_ascii_case(name))
        .map(|h| h.value.as_str().to_string())
}

pub fn body(rq: &mut Request) -> Vec<u8> {
    let mut buf = Vec::new();
    let _ = rq.as_reader().read_to_end(&mut buf);
    buf
}

pub fn hdr(name: &str, value: &str) -> Header {
    Header::from_bytes(name.as_bytes(), value.as_bytes()).expect("valid header")
}

pub fn respond(rq: Request, status: u16, content_type: &str, data: Vec<u8>, extra: Vec<Header>) {
    let mut resp = Response::from_data(data).with_status_code(status);
    resp.add_header(hdr("Content-Type", content_type));
    for h in extra {
        resp.add_header(h);
    }
    let _ = rq.respond(resp);
}
