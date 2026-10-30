"""User time -> device-local time.

Hikvision recorders write local wall-clock time with a misleading `Z` suffix,
so jobs carry naive device-local times and the gateway does the converting.
Agents should pass ISO-8601 times with an offset; a naive time is assumed to
already be device-local.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from .state import GatewayError


def to_device_local(user_time: str | datetime, tz_name: str) -> datetime:
    dt = user_time if isinstance(user_time, datetime) else datetime.fromisoformat(str(user_time))
    if dt.tzinfo is None:
        return dt  # already device-local
    try:
        local = dt.astimezone(ZoneInfo(tz_name))
    except Exception:
        raise GatewayError("bad_tz", f"unknown device time zone {tz_name!r}")
    return local.replace(tzinfo=None)
