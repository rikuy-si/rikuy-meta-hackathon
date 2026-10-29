"""Object storage for recordings: Cloudflare R2 (boto3) or a local stand-in.

The bridge never holds storage credentials and never chooses keys. The
gateway presigns PUT URLs for recordings and GET URLs for agents, and verifies
uploads with a HEAD before telling the bridge it may delete from its spool.

`R2Store` talks to the real R2 S3 endpoint. A plain S3 HEAD gives size but not
SHA-256, so verification is size-exact (and SHA-exact when the store knows
it); the signed-checksum-header hardening stays on the contract's open list.

`LocalStore` is the stand-in used by tests and demos without cloud
credentials: same URL semantics as a presigned S3 PUT (opaque URL, bound to
one key, one method and one length, expiring), HMAC-signed, mounted as a
router on the gateway app itself.
"""

from __future__ import annotations

import hashlib
import hmac
import threading
import time
from typing import Optional

from fastapi import APIRouter, Request, Response

from .state import sha256_hex


class Grant(dict):
    """One presigned upload grant, in the wire shape the bridge expects."""


class R2Store:
    def __init__(self, settings) -> None:
        import boto3
        from botocore.config import Config

        self.bucket = settings.bucket
        self.ttl = settings.presign_ttl_secs
        self.read_ttl = settings.read_ttl_secs
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.endpoint,
            aws_access_key_id=settings.access_key_id,
            aws_secret_access_key=settings.secret_access_key,
            region_name="auto",
            config=Config(signature_version="s3v4"),
        )

    def presign_put(self, key: str, length: int, content_type: str, ttl: Optional[int] = None) -> tuple[str, int]:
        url = self._client.generate_presigned_url(
            "put_object",
            Params={"Bucket": self.bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=ttl or self.ttl,
        )
        return url, int(time.time()) + (ttl or self.ttl)

    def presign_get(self, key: str, ttl: Optional[int] = None) -> str:
        return self._client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=ttl or self.read_ttl
        )

    def head(self, key: str) -> Optional[tuple[int, Optional[str]]]:
        try:
            h = self._client.head_object(Bucket=self.bucket, Key=key)
        except Exception:
            return None
        return int(h["ContentLength"]), None  # SHA-256 not available via plain HEAD

    def put(self, key: str, data: bytes, content_type: str) -> None:
        import io

        self._client.put_object(Bucket=self.bucket, Key=key, Body=io.BytesIO(data), ContentType=content_type)


class LocalStore:
    """HMAC-signed stand-in for R2, mounted at `/__store/<bucket>/<key>`."""

    def __init__(self, secret: str, base_url: str, bucket: str = "rikuy-recordings") -> None:
        self.secret = secret.encode()
        self.base_url = base_url.rstrip("/")
        self.bucket = bucket
        self._objects: dict[str, tuple[bytes, str]] = {}
        self._lock = threading.Lock()
        self.puts = 0
        self.rejected = 0

    # -- signing -----------------------------------------------------------

    def _sig(self, method: str, path: str, expires: int, length: Optional[int]) -> str:
        msg = f"{self.secret.decode()}\n{method}\n{path}\n{expires}\n{length or ''}"
        return hmac.new(self.secret, msg.encode(), hashlib.sha256).hexdigest()

    def presign_put(self, key: str, length: int, content_type: str, ttl: int = 900) -> tuple[str, int]:
        expires = int(time.time()) + max(ttl, 0)
        path = f"/__store/{self.bucket}/{key}"
        sig = self._sig("PUT", path, expires, length)
        url = f"{self.base_url}{path}?X-Local-Expires={expires}&X-Local-Length={length}&X-Local-Signature={sig}"
        return url, expires

    def presign_get(self, key: str, ttl: int = 3600) -> str:
        expires = int(time.time()) + max(ttl, 0)
        path = f"/__store/{self.bucket}/{key}"
        sig = self._sig("GET", path, expires, None)
        return f"{self.base_url}{path}?X-Local-Expires={expires}&X-Local-Signature={sig}"

    # -- gateway-side access (no HTTP) ---------------------------------------

    def head(self, key: str) -> Optional[tuple[int, Optional[str]]]:
        with self._lock:
            obj = self._objects.get(key)
        return (len(obj[0]), sha256_hex(obj[0])) if obj else None

    def put(self, key: str, data: bytes, content_type: str) -> None:
        with self._lock:
            self._objects[key] = (data, content_type)

    def object(self, key: str) -> Optional[tuple[bytes, str]]:
        with self._lock:
            return self._objects.get(key)

    # -- the stand-in HTTP surface -------------------------------------------

    def router(self) -> APIRouter:
        r = APIRouter(prefix=f"/__store/{self.bucket}")

        @r.put("/{key:path}")
        async def put_object(key: str, request: Request) -> Response:
            q = request.query_params
            if not self._check(request, "PUT", key, q, with_length=True):
                self.rejected += 1
                return Response(status_code=403, media_type="application/json", content='{"error":"forbidden"}')
            data = await request.body()
            want_len = int(q["X-Local-Length"])
            if len(data) != want_len:  # presigned PUTs are bound to one length
                self.rejected += 1
                return Response(status_code=400, media_type="application/json", content='{"error":"length mismatch"}')
            ct = request.headers.get("content-type", "application/octet-stream")
            self.put(key, data, ct)
            self.puts += 1
            return Response(status_code=204)

        @r.get("/{key:path}")
        async def get_object(key: str, request: Request) -> Response:
            q = request.query_params
            if not self._check(request, "GET", key, q, with_length=False):
                return Response(status_code=403, media_type="application/json", content='{"error":"forbidden"}')
            obj = self.object(key)
            if obj is None:
                return Response(status_code=404, media_type="application/json", content='{"error":"not found"}')
            return Response(content=obj[0], media_type=obj[1])

        return r

    def _check(self, request: Request, method: str, key: str, q, with_length: bool) -> bool:
        try:
            expires = int(q["X-Local-Expires"])
            sig = q["X-Local-Signature"]
            length = int(q["X-Local-Length"]) if with_length else None
        except (KeyError, ValueError):
            return False
        if expires < time.time():
            return False
        path = f"/__store/{self.bucket}/{key}"
        return hmac.compare_digest(self._sig(method, path, expires, length), sig)
