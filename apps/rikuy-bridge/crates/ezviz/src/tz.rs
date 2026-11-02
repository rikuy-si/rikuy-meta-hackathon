//! Device clock: POSIX TZ rules plus the skew between the device and this host.
//!
//! ONVIF speaks UTC; the bridge contract speaks device-local wall-clock time.
//! The conversion must follow the device's own rules *at the time being
//! converted*, not the offset in force now. The Tejiendo recordings (2026-10-30)
//! were an hour off because the camera had DST enabled; a fixed "current
//! offset" would repeat that mistake for any window across a DST transition.
use chrono::{Datelike, Duration, NaiveDate, NaiveDateTime};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct Rule {
    month: u32,
    /// 1..=5, 5 = last
    week: u32,
    /// 0 = Sunday
    weekday: u32,
    /// Seconds after local midnight (may be negative or > 24h).
    time: i64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PosixTz {
    /// Seconds east of UTC (EST5 -> -18000).
    std_offset: i64,
    dst: Option<(i64, Rule, Rule)>,
}

impl PosixTz {
    pub fn parse(s: &str) -> Option<PosixTz> {
        let mut p = Parser { s: s.trim().as_bytes(), i: 0 };
        p.name()?;
        let std_offset = -p.offset()?;
        if p.done() {
            return Some(PosixTz { std_offset, dst: None });
        }
        p.name()?;
        let dst_offset = if p.peek().map(|c| c == b'+' || c == b'-' || c.is_ascii_digit()).unwrap_or(false) {
            -p.offset()?
        } else {
            std_offset + 3600
        };
        let (start, end) = if p.done() {
            // POSIX leaves this implementation-defined; glibc uses the US rules.
            (Rule { month: 3, week: 2, weekday: 0, time: 7200 }, Rule { month: 11, week: 1, weekday: 0, time: 7200 })
        } else {
            p.expect(b',')?;
            let a = p.rule()?;
            p.expect(b',')?;
            let b = p.rule()?;
            (a, b)
        };
        if !p.done() {
            return None;
        }
        Some(PosixTz { std_offset, dst: Some((dst_offset, start, end)) })
    }

    pub fn has_dst(&self) -> bool {
        self.dst.is_some()
    }

    /// UTC offset (seconds east) in force at this UTC instant.
    pub fn offset_at_utc(&self, utc: NaiveDateTime) -> i64 {
        let Some((dst_off, start, end)) = self.dst else { return self.std_offset };
        let year = (utc + Duration::seconds(self.std_offset)).year();
        let mut in_dst = false;
        // Southern hemisphere: DST starts late in the year and ends the next.
        let wraps = start.month > end.month;
        for y in [year - 1, year] {
            let end_year = if wraps { y + 1 } else { y };
            let (Some(s), Some(e)) = (rule_local(y, start), rule_local(end_year, end)) else { continue };
            // Start is given in standard local time, end in daylight local time.
            let s = s - Duration::seconds(self.std_offset);
            let e = e - Duration::seconds(dst_off);
            if utc >= s && utc < e {
                in_dst = true;
            }
        }
        // Northern rules also need this year's interval when `year - 1` was checked.
        if !wraps && !in_dst {
            if let (Some(s), Some(e)) = (rule_local(year + 1, start), rule_local(year + 1, end)) {
                let s = s - Duration::seconds(self.std_offset);
                let e = e - Duration::seconds(dst_off);
                in_dst = utc >= s && utc < e;
            }
        }
        if in_dst {
            dst_off
        } else {
            self.std_offset
        }
    }

    pub fn to_local(&self, utc: NaiveDateTime) -> NaiveDateTime {
        utc + Duration::seconds(self.offset_at_utc(utc))
    }

    /// Local wall-clock time to UTC. In the repeated fall-back hour the
    /// earlier instant (still DST) wins; in the skipped spring-forward hour the
    /// standard-time reading is used.
    pub fn to_utc(&self, local: NaiveDateTime) -> NaiveDateTime {
        let std_utc = local - Duration::seconds(self.std_offset);
        let Some((dst_off, _, _)) = self.dst else { return std_utc };
        let dst_utc = local - Duration::seconds(dst_off);
        if self.offset_at_utc(dst_utc) == dst_off {
            dst_utc
        } else {
            std_utc
        }
    }
}

fn rule_local(year: i32, r: Rule) -> Option<NaiveDateTime> {
    let first = NaiveDate::from_ymd_opt(year, r.month, 1)?;
    let first_wd = first.weekday().num_days_from_sunday();
    let mut day = 1 + (7 + r.weekday - first_wd) % 7 + (r.week.min(5) - 1) * 7;
    let days_in_month = {
        let next = if r.month == 12 { NaiveDate::from_ymd_opt(year + 1, 1, 1)? } else { NaiveDate::from_ymd_opt(year, r.month + 1, 1)? };
        (next - first).num_days() as u32
    };
    while day > days_in_month {
        day -= 7;
    }
    Some(NaiveDate::from_ymd_opt(year, r.month, day)?.and_hms_opt(0, 0, 0)? + Duration::seconds(r.time))
}

struct Parser<'a> {
    s: &'a [u8],
    i: usize,
}

impl Parser<'_> {
    fn peek(&self) -> Option<u8> {
        self.s.get(self.i).copied()
    }
    fn done(&self) -> bool {
        self.i >= self.s.len()
    }
    fn expect(&mut self, c: u8) -> Option<()> {
        (self.peek()? == c).then(|| self.i += 1)
    }
    fn name(&mut self) -> Option<()> {
        if self.peek()? == b'<' {
            let end = self.s[self.i..].iter().position(|&c| c == b'>')?;
            self.i += end + 1;
            return Some(());
        }
        let start = self.i;
        while self.peek().map(|c| c.is_ascii_alphabetic()).unwrap_or(false) {
            self.i += 1;
        }
        (self.i - start >= 3).then_some(())
    }
    fn num(&mut self) -> Option<i64> {
        let start = self.i;
        while self.peek().map(|c| c.is_ascii_digit()).unwrap_or(false) {
            self.i += 1;
        }
        std::str::from_utf8(&self.s[start..self.i]).ok()?.parse().ok()
    }
    /// [+-]hh[:mm[:ss]] in seconds, POSIX sign (positive = west of UTC).
    fn offset(&mut self) -> Option<i64> {
        let sign = match self.peek()? {
            b'-' => {
                self.i += 1;
                -1
            }
            b'+' => {
                self.i += 1;
                1
            }
            _ => 1,
        };
        let mut secs = self.num()? * 3600;
        if self.peek() == Some(b':') {
            self.i += 1;
            secs += self.num()? * 60;
            if self.peek() == Some(b':') {
                self.i += 1;
                secs += self.num()?;
            }
        }
        Some(sign * secs)
    }
    fn rule(&mut self) -> Option<Rule> {
        // Only the Mm.w.d form; Julian forms are rare on cameras.
        self.expect(b'M')?;
        let month = self.num()? as u32;
        self.expect(b'.')?;
        let week = self.num()? as u32;
        self.expect(b'.')?;
        let weekday = self.num()? as u32;
        let time = if self.peek() == Some(b'/') {
            self.i += 1;
            self.offset()?
        } else {
            7200
        };
        ((1..=12).contains(&month) && (1..=5).contains(&week) && weekday <= 6).then_some(Rule { month, week, weekday, time })
    }
}

/// What the bridge knows about one device's clock.
#[derive(Debug, Clone)]
pub struct DeviceClock {
    /// The device's TZ string as reported, if any.
    pub tz_string: Option<String>,
    pub rules: Option<PosixTz>,
    /// Offset the device reports right now (LocalDateTime - UTCDateTime).
    pub observed_offset: Option<i64>,
    pub daylight_savings: bool,
    /// device UTC - host UTC, seconds. Used for WS-Security `Created`.
    pub skew_secs: i64,
    pub device_utc_at_sync: NaiveDateTime,
}

impl DeviceClock {
    /// The TZ rules are trusted only if they agree with what the device says
    /// its local time is right now; otherwise fall back to the observed offset.
    pub fn rules_consistent(&self) -> bool {
        match (&self.rules, self.observed_offset) {
            (Some(r), Some(obs)) => (r.offset_at_utc(self.device_utc_at_sync) - obs).abs() <= 60,
            (Some(_), None) => true,
            _ => false,
        }
    }

    pub fn offset_now(&self) -> i64 {
        if self.rules_consistent() {
            self.rules.as_ref().unwrap().offset_at_utc(self.device_utc_at_sync)
        } else {
            self.observed_offset.unwrap_or(0)
        }
    }

    pub fn to_utc(&self, local: NaiveDateTime) -> NaiveDateTime {
        if self.rules_consistent() {
            self.rules.as_ref().unwrap().to_utc(local)
        } else {
            local - Duration::seconds(self.observed_offset.unwrap_or(0))
        }
    }

    pub fn to_local(&self, utc: NaiveDateTime) -> NaiveDateTime {
        if self.rules_consistent() {
            self.rules.as_ref().unwrap().to_local(utc)
        } else {
            utc + Duration::seconds(self.observed_offset.unwrap_or(0))
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn t(s: &str) -> NaiveDateTime {
        NaiveDateTime::parse_from_str(s, "%Y-%m-%dT%H:%M:%S").unwrap()
    }

    #[test]
    fn fixed_zone() {
        let z = PosixTz::parse("COT5").unwrap();
        assert!(!z.has_dst());
        assert_eq!(z.to_utc(t("2026-10-30T10:00:00")), t("2026-10-30T15:00:00"));
        let z = PosixTz::parse("<-05>5").unwrap();
        assert_eq!(z.offset_at_utc(t("2026-07-01T00:00:00")), -18000);
        let z = PosixTz::parse("CET-1").unwrap();
        assert_eq!(z.offset_at_utc(t("2026-07-01T00:00:00")), 3600);
    }

    #[test]
    fn us_rules_across_the_2026_fall_back() {
        let z = PosixTz::parse("EST5EDT,M3.2.0,M11.1.0").unwrap();
        // 2026-10-30 (the Tejiendo day): still EDT.
        assert_eq!(z.to_utc(t("2026-10-30T10:28:00")), t("2026-10-30T14:28:00"));
        // 2026-11-02: EST.
        assert_eq!(z.to_utc(t("2026-11-02T10:00:00")), t("2026-11-02T15:00:00"));
        // DST ends Sunday 2026-11-01 02:00 EDT = 06:00 UTC.
        assert_eq!(z.offset_at_utc(t("2026-11-01T05:59:59")), -14400);
        assert_eq!(z.offset_at_utc(t("2026-11-01T06:00:00")), -18000);
        // The repeated hour resolves to the earlier (EDT) instant.
        assert_eq!(z.to_utc(t("2026-11-01T01:30:00")), t("2026-11-01T05:30:00"));
        // Starts Sunday 2026-03-08 02:00 EST.
        assert_eq!(z.offset_at_utc(t("2026-03-08T06:59:59")), -18000);
        assert_eq!(z.offset_at_utc(t("2026-03-08T07:00:00")), -14400);
        assert_eq!(z.to_local(t("2026-10-30T14:28:00")), t("2026-10-30T10:28:00"));
    }

    #[test]
    fn explicit_times_and_southern_hemisphere() {
        let z = PosixTz::parse("CST6CDT,M3.2.0/2:00:00,M11.1.0/2:00:00").unwrap();
        assert_eq!(z.offset_at_utc(t("2026-07-01T00:00:00")), -18000);
        // Chile-style: DST from September to April.
        let z = PosixTz::parse("<-04>4<-03>,M9.1.6/24,M4.1.6/24").unwrap();
        assert_eq!(z.offset_at_utc(t("2026-01-15T12:00:00")), -10800);
        assert_eq!(z.offset_at_utc(t("2026-06-15T12:00:00")), -14400);
    }

    #[test]
    fn rejects_garbage() {
        assert!(PosixTz::parse("").is_none());
        assert!(PosixTz::parse("Bogota").is_none());
        assert!(PosixTz::parse("EST5EDT,J60,J300").is_none());
    }

    #[test]
    fn inconsistent_rules_fall_back_to_observed_offset() {
        let c = DeviceClock {
            tz_string: Some("EST5EDT,M3.2.0,M11.1.0".into()),
            rules: PosixTz::parse("EST5EDT,M3.2.0,M11.1.0"),
            observed_offset: Some(-14400), // device says EDT on 2026-11-02: rules disagree
            daylight_savings: true,
            skew_secs: 0,
            device_utc_at_sync: t("2026-11-02T15:00:00"),
        };
        assert!(!c.rules_consistent());
        assert_eq!(c.to_utc(t("2026-10-30T10:00:00")), t("2026-10-30T14:00:00"));
    }
}
