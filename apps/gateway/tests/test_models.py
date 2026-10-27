"""Contract model tests: the gateway and the bridge must agree exactly."""

import pytest
from pydantic import ValidationError

from rikuy_gateway.models import Credential, Job, Report


def job(**over):
    base = dict(
        id="job-2026-11-02-0001",
        device={"family": "hikvision", "base_url": "http://10.0.0.20"},
        credential={"username": "admin", "password": "correct-horse"},
        kind="download",
        **{"from": "2026-10-29T05:00:00", "to": "2026-10-29T06:00:00"},
        tracks=[101],
    )
    base.update(over)
    return Job.model_validate(base)


def test_wire_format_uses_from_alias_and_drops_none():
    j = job()
    wire = j.wire()
    assert wire["from"] == "2026-10-29T05:00:00"
    assert wire["to"] == "2026-10-29T06:00:00"
    assert "from_" not in wire and "channel" not in wire
    assert wire["device"]["base_url"] == "http://10.0.0.20"
    assert wire["credential"]["password"] == "correct-horse"  # the bridge needs it


def test_unsafe_job_ids_are_rejected():
    for bad in ("../../escape", "a b", "x" * 129, "", "café/1"):
        with pytest.raises(ValidationError):
            job(id=bad)


def test_hikvision_requires_plain_http_lan_url():
    with pytest.raises(ValidationError):
        job(device={"family": "hikvision", "base_url": "https://10.0.0.20"})
    job(device={"family": "hikvision", "base_url": "http://10.0.0.20"})  # ok


def test_times_must_be_naive_device_local():
    with pytest.raises(ValidationError):
        job(**{"from": "2026-10-29T05:00:00Z", "to": "2026-10-29T06:00:00"})
    with pytest.raises(ValidationError):
        job(**{"from": "2026-10-29T05:00:00-05:00", "to": "2026-10-29T06:00:00-05:00"})


def test_kind_field_requirements():
    with pytest.raises(ValidationError):  # snapshot without channel
        job(kind="snapshot")
    with pytest.raises(ValidationError):  # download without range
        job(kind="download", **{"from": None, "to": None})
    with pytest.raises(ValidationError):  # to before from
        job(**{"from": "2026-10-29T06:00:00", "to": "2026-10-29T05:00:00"})
    with pytest.raises(ValidationError):  # bad track id
        job(tracks=[0])
    job(kind="snapshot", channel=2)  # ok


def test_credential_never_prints_its_password():
    c = Credential(username="admin", password="correct-horse")
    assert "correct-horse" not in repr(c)
    assert "correct-horse" not in str(c)
    assert "correct-horse" not in repr(job(kind="snapshot", channel=1))


def test_report_parses_a_real_bridge_report():
    r = Report.model_validate(
        {
            "job_id": "job-2026-11-02-0001",
            "bridge": "site-salon-01",
            "family": "hikvision",
            "status": "partial",
            "error_code": "upload",
            "artifacts": [
                {
                    "kind": "recording",
                    "name": "track-101_20261029T050000_00001.dav",
                    "bytes": 262144040,
                    "sha256": "ab" * 32,
                    "uploaded": True,
                    "object_key": "recordings/site-salon-01/job-1/track-101_20261029T050000_00001.dav",
                }
            ],
            "data": {"found": 4},
        }
    )
    assert r.status == "partial"
    assert r.artifacts[0].object_key.startswith("recordings/")
    # A report the gateway trusts must never carry a credential back.
    assert "password" not in r.model_dump()
