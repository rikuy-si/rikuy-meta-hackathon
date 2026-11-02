//! ONVIF operations the connector needs, on top of [`SoapClient`].
//!
//! - Device (Core): GetSystemDateAndTime, GetDeviceInformation, GetServices
//! - Media2 (Profile T): GetProfiles, GetSnapshotUri
//! - Search (Profile G): FindRecordings, FindEvents (RecordingHistory/Track/State)
//! - Replay (Profile G): GetReplayUri
use std::collections::HashMap;

use chrono::{NaiveDate, NaiveDateTime, Utc};
use rikuy_bridge_common::{BridgeError, Credential};
use serde::Serialize;
use url::Url;

use crate::soap::{fmt_xs_datetime, parse_xs_datetime, SoapClient};
use crate::tz::{DeviceClock, PosixTz};
use crate::xml::{escape, Element};

pub const NS_DEVICE: &str = "http://www.onvif.org/ver10/device/wsdl";
pub const NS_MEDIA2: &str = "http://www.onvif.org/ver20/media/wsdl";
pub const NS_SEARCH: &str = "http://www.onvif.org/ver10/search/wsdl";
pub const NS_REPLAY: &str = "http://www.onvif.org/ver10/replay/wsdl";
const MAX_SEARCH_POLLS: usize = 200;

#[derive(Debug, Clone, Serialize, Default)]
pub struct DeviceInfo {
    pub manufacturer: Option<String>,
    pub model: Option<String>,
    pub firmware: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct Profile {
    pub token: String,
    pub name: Option<String>,
    pub source: String,
    pub encoding: Option<String>,
    pub width: Option<u32>,
    pub height: Option<u32>,
}

impl Profile {
    fn pixels(&self) -> u64 {
        self.width.unwrap_or(0) as u64 * self.height.unwrap_or(0) as u64
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct RecordingInfo {
    pub token: String,
    pub source_id: Option<String>,
    pub name: Option<String>,
    pub earliest_utc: Option<NaiveDateTime>,
    pub latest_utc: Option<NaiveDateTime>,
    pub video_track: Option<String>,
}

#[derive(Debug, Clone)]
pub struct TrackEvent {
    pub time_utc: NaiveDateTime,
    pub data_present: bool,
    pub start_state: bool,
}

pub struct OnvifDevice {
    pub soap: SoapClient,
    device_url: Url,
    pub clock: DeviceClock,
    services: HashMap<String, String>,
    pub info: DeviceInfo,
}

impl OnvifDevice {
    /// Sync the clock (unauthenticated, as the spec requires), then identify
    /// the device and its services with the job's credential.
    pub fn connect(base_url: &str, credential: Credential) -> Result<OnvifDevice, BridgeError> {
        let mut soap = SoapClient::new(base_url, credential)?;
        let given = Url::parse(base_url).map_err(|e| BridgeError::Usage(e.to_string()))?;
        let device_url = if given.path().is_empty() || given.path() == "/" {
            soap.origin.join("/onvif/device_service").unwrap()
        } else {
            soap.rebase_http(given.as_str())?
        };
        let clock = sync_clock(&mut soap, &device_url)?;
        soap.skew_secs = clock.skew_secs;
        let mut dev = OnvifDevice { soap, device_url, clock, services: HashMap::new(), info: DeviceInfo::default() };
        let r = dev.call_device("<tds:GetDeviceInformation/>")?;
        dev.info = DeviceInfo {
            manufacturer: r.text_of("Manufacturer").map(String::from),
            model: r.text_of("Model").map(String::from),
            firmware: r.text_of("FirmwareVersion").map(String::from),
        };
        let r = dev.call_device("<tds:GetServices><tds:IncludeCapability>false</tds:IncludeCapability></tds:GetServices>")?;
        for s in r.children_named("Service") {
            if let (Some(ns), Some(x)) = (s.text_of("Namespace"), s.text_of("XAddr")) {
                dev.services.insert(ns.to_string(), x.to_string());
            }
        }
        Ok(dev)
    }

    fn call_device(&mut self, body: &str) -> Result<Element, BridgeError> {
        let url = self.device_url.clone();
        self.soap.call(&url, body, true)
    }

    pub fn has_service(&self, ns: &str) -> bool {
        self.services.contains_key(ns)
    }

    fn service(&self, ns: &str, what: &str) -> Result<Url, BridgeError> {
        let x = self
            .services
            .get(ns)
            .ok_or_else(|| BridgeError::Unsupported(format!("device does not offer the ONVIF {what} service ({ns})")))?;
        self.soap.rebase_http(x)
    }

    fn call(&mut self, ns: &str, what: &str, body: &str) -> Result<Element, BridgeError> {
        let url = self.service(ns, what)?;
        self.soap.call(&url, body, true)
    }

    /// Media2 profiles (Profile T: H.264 and H.265).
    pub fn profiles(&mut self) -> Result<Vec<Profile>, BridgeError> {
        let r = self.call(NS_MEDIA2, "Media2", "<tr2:GetProfiles><tr2:Type>All</tr2:Type></tr2:GetProfiles>")?;
        let mut out = Vec::new();
        for p in r.children_named("Profiles") {
            let Some(token) = p.attr("token") else { continue };
            let Some(source) = p.find("VideoSource").and_then(|v| v.text_of("SourceToken")) else { continue };
            let enc = p.find("VideoEncoder");
            out.push(Profile {
                token: token.to_string(),
                name: p.child("Name").map(|n| n.trimmed().to_string()),
                source: source.to_string(),
                encoding: enc.and_then(|e| e.text_of("Encoding")).map(String::from),
                width: enc.and_then(|e| e.find("Resolution")).and_then(|r| r.text_of("Width")).and_then(|w| w.parse().ok()),
                height: enc.and_then(|e| e.find("Resolution")).and_then(|r| r.text_of("Height")).and_then(|w| w.parse().ok()),
            });
        }
        Ok(out)
    }

    pub fn snapshot_uri(&mut self, profile: &str) -> Result<Url, BridgeError> {
        let body = format!("<tr2:GetSnapshotUri><tr2:ProfileToken>{}</tr2:ProfileToken></tr2:GetSnapshotUri>", escape(profile));
        let r = self.call(NS_MEDIA2, "Media2", &body)?;
        let uri = r.text_of("Uri").ok_or_else(|| BridgeError::Protocol("GetSnapshotUri: no Uri".into()))?;
        self.soap.rebase_http(uri)
    }

    /// Every recording on the device (Profile G search).
    pub fn recordings(&mut self) -> Result<Vec<RecordingInfo>, BridgeError> {
        let r = self.call(
            NS_SEARCH,
            "Search",
            "<tse:FindRecordings><tse:Scope/><tse:KeepAliveTime>PT10S</tse:KeepAliveTime></tse:FindRecordings>",
        )?;
        let token = r.text_of("SearchToken").ok_or_else(|| BridgeError::Protocol("FindRecordings: no SearchToken".into()))?.to_string();
        let mut out = Vec::new();
        let result = (|| {
            for _ in 0..MAX_SEARCH_POLLS {
                let body = format!(
                    "<tse:GetRecordingSearchResults><tse:SearchToken>{}</tse:SearchToken><tse:WaitTime>PT2S</tse:WaitTime></tse:GetRecordingSearchResults>",
                    escape(&token)
                );
                let r = self.call(NS_SEARCH, "Search", &body)?;
                let list = r.find("ResultList").unwrap_or(&r);
                for ri in list.children_named("RecordingInformation") {
                    let Some(tok) = ri.text_of("RecordingToken") else { continue };
                    let video_track = ri
                        .children_named("Track")
                        .find(|t| t.text_of("TrackType") == Some("Video"))
                        .and_then(|t| t.text_of("TrackToken"))
                        .map(String::from);
                    out.push(RecordingInfo {
                        token: tok.to_string(),
                        source_id: ri.child("Source").and_then(|s| s.text_of("SourceId")).map(String::from),
                        name: ri.child("Source").and_then(|s| s.text_of("Name")).map(String::from),
                        earliest_utc: ri.text_of("EarliestRecording").and_then(parse_xs_datetime),
                        latest_utc: ri.text_of("LatestRecording").and_then(parse_xs_datetime),
                        video_track,
                    });
                }
                if list.text_of("SearchState") == Some("Completed") {
                    return Ok(());
                }
            }
            Err(BridgeError::Protocol("FindRecordings: search never completed".into()))
        })();
        self.end_search(&token);
        result.map(|_| out)
    }

    /// Track data-present transitions for one recording in a UTC window.
    pub fn track_events(
        &mut self,
        recording: &str,
        from_utc: NaiveDateTime,
        to_utc: NaiveDateTime,
    ) -> Result<Vec<TrackEvent>, BridgeError> {
        let body = format!(
            concat!(
                "<tse:FindEvents><tse:StartPoint>{}</tse:StartPoint><tse:EndPoint>{}</tse:EndPoint>",
                "<tse:Scope><tt:IncludedRecordings>{}</tt:IncludedRecordings></tse:Scope>",
                "<tse:SearchFilter><tt:TopicExpression xmlns:tns1=\"http://www.onvif.org/ver10/topics\" ",
                "Dialect=\"http://www.onvif.org/ver10/tev/topicExpression/ConcreteSet\">tns1:RecordingHistory/Track/State</tt:TopicExpression></tse:SearchFilter>",
                "<tse:IncludeStartState>true</tse:IncludeStartState><tse:KeepAliveTime>PT10S</tse:KeepAliveTime></tse:FindEvents>"
            ),
            fmt_xs_datetime(from_utc),
            fmt_xs_datetime(to_utc),
            escape(recording)
        );
        let r = self.call(NS_SEARCH, "Search", &body)?;
        let token = r.text_of("SearchToken").ok_or_else(|| BridgeError::Protocol("FindEvents: no SearchToken".into()))?.to_string();
        let mut out = Vec::new();
        let result = (|| {
            for _ in 0..MAX_SEARCH_POLLS {
                let body = format!(
                    "<tse:GetEventSearchResults><tse:SearchToken>{}</tse:SearchToken><tse:WaitTime>PT2S</tse:WaitTime></tse:GetEventSearchResults>",
                    escape(&token)
                );
                let r = self.call(NS_SEARCH, "Search", &body)?;
                let list = r.find("ResultList").unwrap_or(&r);
                for ev in list.children_named("Result") {
                    if ev.text_of("RecordingToken").map(|t| t != recording).unwrap_or(false) {
                        continue;
                    }
                    let Some(time) = ev.text_of("Time").and_then(parse_xs_datetime) else { continue };
                    let mut items = Vec::new();
                    ev.find_all("SimpleItem", &mut items);
                    let Some(present) = items
                        .iter()
                        .find(|i| i.attr("Name") == Some("IsDataPresent"))
                        .and_then(|i| i.attr("Value"))
                        .map(|v| v.eq_ignore_ascii_case("true"))
                    else {
                        continue;
                    };
                    let track = ev.text_of("TrackToken").map(String::from);
                    out.push((track, TrackEvent { time_utc: time, data_present: present, start_state: ev.text_of("StartStateEvent") == Some("true") }));
                }
                if list.text_of("SearchState") == Some("Completed") {
                    return Ok(());
                }
            }
            Err(BridgeError::Protocol("FindEvents: search never completed".into()))
        })();
        self.end_search(&token);
        result?;
        Ok(out.into_iter().map(|(_, e)| e).collect())
    }

    fn end_search(&mut self, token: &str) {
        let body = format!("<tse:EndSearch><tse:SearchToken>{}</tse:SearchToken></tse:EndSearch>", escape(token));
        let _ = self.call(NS_SEARCH, "Search", &body);
    }

    /// RTSP URI for replaying a recording. The host is rebased onto the
    /// address the bridge reaches the device at; the RTSP port is kept.
    pub fn replay_uri(&mut self, recording: &str) -> Result<Url, BridgeError> {
        let body = format!(
            concat!(
                "<trp:GetReplayUri><trp:StreamSetup><tt:Stream>RTP-Unicast</tt:Stream>",
                "<tt:Transport><tt:Protocol>RTSP</tt:Protocol></tt:Transport></trp:StreamSetup>",
                "<trp:RecordingToken>{}</trp:RecordingToken></trp:GetReplayUri>"
            ),
            escape(recording)
        );
        let r = self.call(NS_REPLAY, "Replay", &body)?;
        let uri = r.text_of("Uri").ok_or_else(|| BridgeError::Protocol("GetReplayUri: no Uri".into()))?;
        let mut u = Url::parse(uri).map_err(|e| BridgeError::Protocol(format!("replay uri {uri}: {e}")))?;
        if u.scheme() != "rtsp" {
            return Err(BridgeError::Unsupported(format!("replay uri scheme {}", u.scheme())));
        }
        u.set_host(Some(self.soap.host())).map_err(|e| BridgeError::Protocol(e.to_string()))?;
        Ok(u)
    }
}

fn sync_clock(soap: &mut SoapClient, device_url: &Url) -> Result<DeviceClock, BridgeError> {
    let r = soap.call(device_url, "<tds:GetSystemDateAndTime/>", false)?;
    let host_now = Utc::now().naive_utc();
    let sdt = r.find("SystemDateAndTime").unwrap_or(&r);
    let utc = sdt.child("UTCDateTime").and_then(onvif_datetime);
    let local = sdt.child("LocalDateTime").and_then(onvif_datetime);
    let tz_string = sdt.child("TimeZone").and_then(|t| t.text_of("TZ")).map(String::from);
    let device_utc = utc.unwrap_or(host_now);
    Ok(DeviceClock {
        rules: tz_string.as_deref().and_then(PosixTz::parse),
        tz_string,
        observed_offset: match (utc, local) {
            // Round to the minute: the two readings are not taken atomically.
            (Some(u), Some(l)) => Some(((l - u).num_seconds() as f64 / 60.0).round() as i64 * 60),
            _ => None,
        },
        daylight_savings: sdt.text_of("DaylightSavings") == Some("true"),
        skew_secs: (device_utc - host_now).num_seconds(),
        device_utc_at_sync: device_utc,
    })
}

fn onvif_datetime(e: &Element) -> Option<NaiveDateTime> {
    let d = e.child("Date")?;
    let t = e.child("Time")?;
    let n = |el: &Element, k: &str| el.text_of(k).and_then(|v| v.parse::<u32>().ok());
    NaiveDate::from_ymd_opt(n(d, "Year")? as i32, n(d, "Month")?, n(d, "Day")?)?.and_hms_opt(n(t, "Hour")?, n(t, "Minute")?, n(t, "Second")?)
}

/// One channel = one video source; its main profile is the highest resolution.
pub fn channels(profiles: &[Profile]) -> Vec<(String, Profile)> {
    let mut out: Vec<(String, Profile)> = Vec::new();
    for p in profiles {
        match out.iter_mut().find(|(s, _)| *s == p.source) {
            Some((_, best)) if p.pixels() > best.pixels() => *best = p.clone(),
            Some(_) => {}
            None => out.push((p.source.clone(), p.clone())),
        }
    }
    out
}

/// Recorded intervals inside `[from, to]` from data-present transitions.
/// With no events at all, the recording's earliest..latest span is used.
pub fn recorded_ranges(
    events: &[TrackEvent],
    from: NaiveDateTime,
    to: NaiveDateTime,
    earliest: Option<NaiveDateTime>,
    latest: Option<NaiveDateTime>,
) -> Vec<(NaiveDateTime, NaiveDateTime)> {
    let lo = earliest.map(|e| e.max(from)).unwrap_or(from);
    let hi = latest.map(|l| l.min(to)).unwrap_or(to);
    if lo >= hi {
        return vec![];
    }
    if events.is_empty() {
        return vec![(lo, hi)];
    }
    let mut ev: Vec<&TrackEvent> = events.iter().collect();
    ev.sort_by_key(|e| (e.time_utc, !e.start_state));
    let mut out = Vec::new();
    let mut open: Option<NaiveDateTime> = None;
    for e in ev {
        let t = e.time_utc.max(lo);
        match (e.data_present, open) {
            (true, None) => open = Some(t),
            (false, Some(s)) => {
                let end = t.min(hi);
                if end > s {
                    out.push((s, end));
                }
                open = None;
            }
            _ => {}
        }
    }
    if let Some(s) = open {
        if hi > s {
            out.push((s, hi));
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn t(s: &str) -> NaiveDateTime {
        NaiveDateTime::parse_from_str(s, "%Y-%m-%dT%H:%M:%S").unwrap()
    }
    fn ev(s: &str, p: bool, start: bool) -> TrackEvent {
        TrackEvent { time_utc: t(s), data_present: p, start_state: start }
    }

    #[test]
    fn ranges_from_events_with_a_gap() {
        let e = vec![
            ev("2026-10-30T14:28:00", true, true),
            ev("2026-10-30T14:30:00", false, false),
            ev("2026-10-30T14:35:00", true, false),
        ];
        let r = recorded_ranges(&e, t("2026-10-30T14:28:00"), t("2026-10-30T14:37:00"), None, None);
        assert_eq!(r, vec![(t("2026-10-30T14:28:00"), t("2026-10-30T14:30:00")), (t("2026-10-30T14:35:00"), t("2026-10-30T14:37:00"))]);
    }

    #[test]
    fn ranges_without_events_use_the_recording_span() {
        let r = recorded_ranges(&[], t("2026-10-30T10:00:00"), t("2026-10-30T12:00:00"), Some(t("2026-10-30T11:00:00")), None);
        assert_eq!(r, vec![(t("2026-10-30T11:00:00"), t("2026-10-30T12:00:00"))]);
        let r = recorded_ranges(&[ev("2026-10-30T10:00:00", false, true)], t("2026-10-30T10:00:00"), t("2026-10-30T11:00:00"), None, None);
        assert!(r.is_empty());
    }

    #[test]
    fn main_profile_is_highest_resolution_per_source() {
        let p = |tok: &str, src: &str, w: u32| Profile { token: tok.into(), name: None, source: src.into(), encoding: None, width: Some(w), height: Some(w / 2) };
        let ch = channels(&[p("sub1", "VS1", 640), p("main1", "VS1", 2880), p("main2", "VS2", 1920)]);
        assert_eq!(ch.len(), 2);
        assert_eq!(ch[0].1.token, "main1");
        assert_eq!(ch[1].1.token, "main2");
    }
}
