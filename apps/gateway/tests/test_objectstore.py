"""Object storage: presigned grants, verification, spool delete list."""

import time

import pytest
from fastapi.testclient import TestClient

from rikuy_gateway.app import create_app
from rikuy_gateway.config import R2Settings, Settings
from rikuy_gateway.objectstore import R2Store

BRIDGE = "site-salon-01"
TOKEN = "bridge-token-test"
ADMIN = {"Authorization": "Bearer rikuy-admin-dev"}
BASE = "http://testserver"  # TestClient's world


@pytest.fixture()
def world(tmp_path):
    s = Settings.dev(tmp=tmp_path, base=BASE)
    app = create_app(s)
    app.state.gateway.enroll_bridge(BRIDGE, TOKEN)
    return app


@pytest.fixture()
def client(world):
    return TestClient(world)


def hdr(token=TOKEN):
    return {"Authorization": f"Bearer {token}"}


def ask_grant(client, job="job-1", name="track-101_x.dav", n=1024, sha="ab" * 32):
    r = client.post(
        f"/v1/bridge/jobs/{job}/uploads",
        json={"bridge": BRIDGE, "artifacts": [{"name": name, "bytes": n, "sha256": sha}]},
        headers=hdr(),
    )
    return r


def test_uploads_404_when_no_object_storage(tmp_path):
    s = Settings.dev(tmp=tmp_path)
    s.store = "none"
    app = create_app(s)
    app.state.gateway.enroll_bridge(BRIDGE, TOKEN)
    c = TestClient(app)
    assert ask_grant(c).status_code == 404


def test_grant_shape_and_key_choice(client):
    r = ask_grant(client)
    assert r.status_code == 200
    g = r.json()["grants"][0]
    assert g["key"] == f"recordings/{BRIDGE}/job-1/track-101_x.dav"  # backend chooses keys
    assert g["method"] == "PUT"
    assert g["url"].startswith(BASE + "/__store/rikuy-recordings/")
    assert g["headers"]["Content-Type"] == "application/octet-stream"
    assert g["expires_at"] > time.time()


def test_presigned_put_roundtrip_with_length_and_expiry(client):
    data = b"IMKH" + b"x" * 1020
    r = ask_grant(client, n=len(data), sha=None or __import__("hashlib").sha256(data).hexdigest())
    url = r.json()["grants"][0]["url"]
    ok = client.put(url, content=data, headers={"Content-Type": "application/octet-stream"})
    assert ok.status_code == 204
    # wrong length is rejected: the URL is bound to one size
    bad = client.put(url, content=b"short", headers={"Content-Type": "application/octet-stream"})
    assert bad.status_code == 400
    # tampered signature is rejected
    tampered = url[:-1] + ("0" if url[-1] != "0" else "1")
    assert client.put(tampered, content=data).status_code == 403


def test_expired_grant_is_refused(client):
    data = b"y" * 32
    sha = __import__("hashlib").sha256(data).hexdigest()
    store = client.app.state.gateway.objectstore
    url, _ = store.presign_put(f"recordings/{BRIDGE}/job-9/x.dav", len(data), "application/octet-stream", ttl=-60)
    r = client.put(url, content=data)
    assert r.status_code == 403


def test_already_stored_files_are_deduped(client):
    data = b"z" * 64
    sha = __import__("hashlib").sha256(data).hexdigest()
    r = ask_grant(client, job="job-2", n=len(data), sha=sha)
    g = r.json()["grants"][0]
    assert client.put(g["url"], content=data, headers={"Content-Type": "application/octet-stream"}).status_code == 204
    again = ask_grant(client, job="job-2", n=len(data), sha=sha)
    body = again.json()
    assert body["grants"] == []
    assert body["stored"][0]["name"] == "track-101_x.dav"


def test_report_delete_list_only_after_head_verification(client):
    data = b"w" * 128
    sha = __import__("hashlib").sha256(data).hexdigest()
    r = ask_grant(client, job="job-3", n=len(data), sha=sha)
    g = r.json()["grants"][0]
    client.put(g["url"], content=data, headers={"Content-Type": "application/octet-stream"})
    report = {
        "job_id": "job-3",
        "bridge": BRIDGE,
        "family": "hikvision",
        "status": "succeeded",
        "artifacts": [
            {"kind": "recording", "name": "track-101_x.dav", "bytes": len(data), "sha256": sha,
             "uploaded": True, "object_key": g["key"]}
        ],
    }
    r = client.post("/v1/bridge/jobs/job-3/report", json=report, headers=hdr())
    assert r.status_code == 200
    assert r.json() == {"delete": ["track-101_x.dav"]}
    # a report whose bytes do not match the stored object must not free the spool
    report["artifacts"][0]["bytes"] = 999
    r = client.post("/v1/bridge/jobs/job-3/report", json=report, headers=hdr())
    assert r.status_code == 204


def test_r2_store_presigns_without_network():
    s = R2Settings(
        endpoint="https://acct.r2.cloudflarestorage.com",
        access_key_id="AKIA-test",
        secret_access_key="secret-test",
    )
    store = R2Store(s)
    url, expires = store.presign_put("recordings/b/j/x.dav", 10, "application/octet-stream")
    assert url.startswith("https://acct.r2.cloudflarestorage.com/rikuy-recordings/recordings/b/j/x.dav?")
    assert "X-Amz-Signature=" in url and "X-Amz-Expires=" in url
    read = store.presign_get("recordings/b/j/x.dav")
    assert "X-Amz-Signature=" in read
