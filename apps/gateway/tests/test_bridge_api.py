"""Bridge-facing API: auth, polling, reports, artifacts, leases."""

import pytest
from fastapi.testclient import TestClient

from rikuy_gateway.app import create_app
from rikuy_gateway.config import Settings
from rikuy_gateway.models import Report
from rikuy_gateway.state import GatewayState

BRIDGE = "site-salon-01"
TOKEN = "bridge-token-test"
ADMIN = {"Authorization": "Bearer rikuy-admin-dev"}


@pytest.fixture()
def world(tmp_path):
    settings = Settings.dev(tmp=tmp_path)
    app = create_app(settings)
    app.state.gateway.enroll_bridge(BRIDGE, TOKEN, family="hikvision")
    return app


@pytest.fixture()
def client(world):
    return TestClient(world)


def hdr(token=TOKEN):
    return {"Authorization": f"Bearer {token}"}


def submit(client, job_id, kind="list_cameras", extra=None):
    job = {
        "id": job_id,
        "device": {"family": "hikvision", "base_url": "http://10.0.0.20"},
        "credential": {"username": "admin", "password": "correct-horse"},
        "kind": kind,
    }
    job.update(extra or {})
    return client.post("/v1/admin/jobs", json={"bridge": BRIDGE, "job": job}, headers=ADMIN)


def snapshot_report(job_id="j1"):
    return Report.model_validate(
        {
            "job_id": job_id,
            "bridge": BRIDGE,
            "family": "hikvision",
            "status": "succeeded",
            "artifacts": [{"kind": "snapshot", "name": f"snapshot-cam2.jpg", "bytes": 3, "sha256": "00" * 32, "uploaded": True}],
        }
    )


def test_poll_requires_the_bridge_token(client):
    assert client.get(f"/v1/bridge/jobs/next?bridge={BRIDGE}").status_code == 401
    assert client.get(f"/v1/bridge/jobs/next?bridge={BRIDGE}", headers=hdr("nope")).status_code == 401


def test_token_identifies_exactly_one_bridge(client):
    submit(client, "j1")
    other = {"Authorization": "Bearer " + TOKEN, }
    r = client.get("/v1/bridge/jobs/next?bridge=someone-else", headers=other)
    assert r.status_code == 403


def test_next_returns_wire_job_then_204(client):
    assert client.get(f"/v1/bridge/jobs/next?bridge={BRIDGE}", headers=hdr()).status_code == 204
    submit(client, "j1", "download", {"from": "2026-10-29T05:00:00", "to": "2026-10-29T06:00:00", "tracks": [101]})
    r = client.get(f"/v1/bridge/jobs/next?bridge={BRIDGE}", headers=hdr())
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "j1"
    assert body["from"] == "2026-10-29T05:00:00"  # the alias the bridge parses
    assert body["device"]["family"] == "hikvision"
    assert client.get(f"/v1/bridge/jobs/next?bridge={BRIDGE}", headers=hdr()).status_code == 204


def test_duplicate_and_mismatched_jobs_are_refused(client):
    submit(client, "j1")
    assert submit(client, "j1").status_code == 409
    job = {
        "id": "j2",
        "device": {"family": "ezviz", "base_url": "http://10.0.0.20"},
        "credential": {"username": "a", "password": "b"},
        "kind": "list_cameras",
    }
    r = client.post("/v1/admin/jobs", json={"bridge": BRIDGE, "job": job}, headers=ADMIN)
    assert r.status_code == 400 and "family" in r.json()["detail"]["error"]


def test_revoked_bridge_gets_401_and_the_daemon_will_stop(world, client):
    submit(client, "j1")
    world.state.gateway.revoke_bridge(BRIDGE)
    assert client.get(f"/v1/bridge/jobs/next?bridge={BRIDGE}", headers=hdr()).status_code == 401


def test_report_is_recorded_and_job_id_must_match(client):
    submit(client, "j1")
    client.get(f"/v1/bridge/jobs/next?bridge={BRIDGE}", headers=hdr())
    r = client.post(f"/v1/bridge/jobs/j1/report", json=snapshot_report().model_dump(exclude_none=True), headers=hdr())
    assert r.status_code == 204
    got = client.get("/v1/admin/jobs/j1/report", headers=ADMIN).json()
    assert got["status"] == "succeeded"
    bad = snapshot_report("j1")
    r = client.post("/v1/bridge/jobs/OTHER/report", json=bad.model_dump(exclude_none=True), headers=hdr())
    assert r.status_code == 400


def test_snapshot_artifact_roundtrip_and_hash(client):
    submit(client, "j1", "snapshot", {"channel": 2})
    client.get(f"/v1/bridge/jobs/next?bridge={BRIDGE}", headers=hdr())
    r = client.put(
        "/v1/bridge/jobs/j1/artifacts/snapshot-cam2.jpg",
        content=b"\xff\xd8fake-jpeg",
        headers={**hdr(), "Content-Type": "image/jpeg"},
    )
    assert r.status_code == 204
    stored = client.app.state.gateway.artifact("j1", "snapshot-cam2.jpg")
    assert stored.data == b"\xff\xd8fake-jpeg"
    assert stored.content_type == "image/jpeg"
    # traversal-ish names are refused
    assert client.put("/v1/bridge/jobs/j1/artifacts/..%2Fescape", content=b"x", headers=hdr()).status_code in (400, 404)
    assert client.put("/v1/bridge/jobs/j1/artifacts/.hidden", content=b"x", headers=hdr()).status_code == 400


def test_unreported_job_returns_to_the_queue_when_its_lease_expires(world, client):
    from datetime import datetime, timedelta, timezone

    submit(client, "j1")
    client.get(f"/v1/bridge/jobs/next?bridge={BRIDGE}", headers=hdr())  # leased
    # force the lease into the past
    gw = world.state.gateway
    gw.leases["j1"].expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    r = client.get(f"/v1/bridge/jobs/next?bridge={BRIDGE}", headers=hdr())
    assert r.status_code == 200 and r.json()["id"] == "j1"  # re-leased, not lost
    assert any(e["action"] == "lease_expired" for e in gw.audit.events)


def test_audit_log_records_the_flow_without_secrets(world, client):
    submit(client, "j1", "snapshot", {"channel": 2})
    client.get(f"/v1/bridge/jobs/next?bridge={BRIDGE}", headers=hdr())
    client.put("/v1/bridge/jobs/j1/artifacts/snapshot-cam2.jpg", content=b"x", headers=hdr())
    client.post("/v1/bridge/jobs/j1/report", json=snapshot_report().model_dump(exclude_none=True), headers=hdr())
    raw = world.state.settings.audit_path.read_text()
    assert "correct-horse" not in raw  # the job credential never reaches disk
    assert "bridge-token-test" not in raw  # full tokens are redacted too
    actions = [e["action"] for e in world.state.gateway.audit.events]
    assert "job_submitted" in actions and "job_reported" in actions
