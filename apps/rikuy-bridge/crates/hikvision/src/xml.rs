//! ISAPI XML bodies (requests are templated, responses deserialized).
use chrono::NaiveDateTime;
use serde::Deserialize;

/// ISAPI timestamps carry a `Z` suffix but are the DVR's local wall-clock
/// time. We keep them as naive local times and never convert them as UTC.
pub const ISAPI_TS: &str = "%Y-%m-%dT%H:%M:%SZ";

pub fn fmt_ts(t: NaiveDateTime) -> String {
    t.format(ISAPI_TS).to_string()
}

pub fn parse_ts(s: &str) -> Option<NaiveDateTime> {
    NaiveDateTime::parse_from_str(s.trim(), ISAPI_TS)
        .or_else(|_| NaiveDateTime::parse_from_str(s.trim().trim_end_matches('Z'), "%Y-%m-%dT%H:%M:%S"))
        .ok()
}

pub fn escape(s: &str) -> String {
    s.replace('&', "&amp;").replace('<', "&lt;").replace('>', "&gt;").replace('"', "&quot;")
}

pub fn search_request(search_id: &str, tracks: &[u32], from: NaiveDateTime, to: NaiveDateTime, max: usize, position: usize) -> String {
    let mut track_list = String::new();
    for t in tracks {
        track_list.push_str(&format!("<trackID>{t}</trackID>"));
    }
    // `searchResultPostion` is Hikvision's spelling.
    format!(
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\
<CMSearchDescription version=\"1.0\" xmlns=\"http://www.isapi.org/ver20/XMLSchema\">\
<searchID>{search_id}</searchID>\
<trackList>{track_list}</trackList>\
<timeSpanList><timeSpan><startTime>{}</startTime><endTime>{}</endTime></timeSpan></timeSpanList>\
<maxResults>{max}</maxResults>\
<searchResultPostion>{position}</searchResultPostion>\
<metadataList><metadataDescriptor>//recordType.meta.std-cgi.com</metadataDescriptor></metadataList>\
</CMSearchDescription>",
        fmt_ts(from),
        fmt_ts(to)
    )
}

pub fn download_request(playback_uri: &str) -> String {
    format!(
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?><downloadRequest version=\"1.0\" xmlns=\"http://www.isapi.org/ver20/XMLSchema\"><playbackURI>{}</playbackURI></downloadRequest>",
        escape(playback_uri)
    )
}

#[derive(Debug, Deserialize)]
pub struct TrackList {
    #[serde(rename = "Track", default)]
    pub tracks: Vec<TrackXml>,
}

#[derive(Debug, Deserialize)]
pub struct TrackXml {
    pub id: u32,
    #[serde(rename = "Channel")]
    pub channel: Option<u32>,
    #[serde(rename = "Enable")]
    pub enable: Option<bool>,
    #[serde(rename = "Description")]
    pub description: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct SearchResult {
    #[serde(rename = "responseStatusStrg")]
    pub status: String,
    #[serde(rename = "numOfMatches", default)]
    pub num_matches: usize,
    #[serde(rename = "matchList")]
    pub match_list: Option<MatchList>,
}

#[derive(Debug, Deserialize, Default)]
pub struct MatchList {
    #[serde(rename = "searchMatchItem", default)]
    pub items: Vec<MatchItem>,
}

#[derive(Debug, Deserialize)]
pub struct MatchItem {
    #[serde(rename = "trackID")]
    pub track: u32,
    #[serde(rename = "timeSpan")]
    pub span: TimeSpan,
    #[serde(rename = "mediaSegmentDescriptor")]
    pub media: MediaSegment,
}

#[derive(Debug, Deserialize)]
pub struct TimeSpan {
    #[serde(rename = "startTime")]
    pub start: String,
    #[serde(rename = "endTime")]
    pub end: String,
}

#[derive(Debug, Deserialize)]
pub struct MediaSegment {
    #[serde(rename = "playbackURI")]
    pub playback_uri: String,
}

#[derive(Debug, Deserialize)]
pub struct ResponseStatus {
    #[serde(rename = "statusCode")]
    pub code: Option<u32>,
    #[serde(rename = "statusString")]
    pub string: Option<String>,
}

#[cfg(test)]
mod tests {
    use super::*;

    const MORE: &str = include_str!("../../../mocks/fixtures/search-result-more.xml");
    const NONE: &str = include_str!("../../../mocks/fixtures/search-result-none.xml");
    const TRACKS: &str = include_str!("../../../mocks/fixtures/tracks.xml");

    #[test]
    fn parses_search_page_and_unescapes_uri() {
        let r: SearchResult = quick_xml::de::from_str(MORE).unwrap();
        assert_eq!(r.status, "MORE");
        let items = r.match_list.unwrap().items;
        assert_eq!(items.len(), 1);
        assert_eq!(items[0].track, 101);
        assert!(items[0].media.playback_uri.contains("&endtime=20261029T051500Z&name="));
        assert_eq!(parse_ts(&items[0].span.start).unwrap().to_string(), "2026-10-29 05:00:00");
    }

    #[test]
    fn parses_no_matches() {
        let r: SearchResult = quick_xml::de::from_str(NONE).unwrap();
        assert_eq!(r.status, "NO MATCHES");
        assert!(r.match_list.is_none());
    }

    #[test]
    fn parses_tracks() {
        let t: TrackList = quick_xml::de::from_str(TRACKS).unwrap();
        assert_eq!(t.tracks.iter().map(|t| t.id).collect::<Vec<_>>(), vec![101, 201]);
        assert_eq!(t.tracks[1].channel, Some(2));
    }

    #[test]
    fn download_request_escapes_query() {
        let x = download_request("rtsp://h/Streaming/tracks/101/?a=1&b=2");
        assert!(x.contains("?a=1&amp;b=2</playbackURI>"));
    }
}
