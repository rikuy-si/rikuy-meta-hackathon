"""The bridge-facing REST API (backend-contract.md) plus a small admin API.

Bridges only ever make outbound calls to `/v1/bridge/*`. The admin API is for
operators and tests: enrollment, job submission, report inspection.
"""

from __future__ import annotations

from typing import Annotated, Any, Optional

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response

from .models import Job, Report
from .state import GatewayError, GatewayState, is_plain_name


def _err(status: int, code: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"error": code})


def bridge_router(state: GatewayState, settings) -> APIRouter:
    r = APIRouter(prefix="/v1/bridge")

    def auth(authorization: Optional[str], bridge_query: Optional[str] = None):
        if not authorization or not authorization.startswith("Bearer "):
            raise _err(401, "unauthorized")
        b = state.bridge_for_token(authorization[7:])
        if b is None or b.revoked:
            # 401/403 must stop the daemon (exit 77): never let it keep polling.
            raise _err(401, "unauthorized")
        if bridge_query is not None and bridge_query != b.id:
            raise _err(403, "bridge mismatch")
        return b

    @r.get("/jobs/next")
    def jobs_next(
        bridge: Annotated[str, Query()],
        authorization: Annotated[Optional[str], Header()] = None,
    ) -> Response:
        auth(authorization, bridge)
        job = state.next_job(bridge)
        if job is None:
            return Response(status_code=204)
        return Response(content=job.model_dump_json(by_alias=True, exclude_none=True), media_type="application/json")

    @r.post("/jobs/{job_id}/report")
    def job_report(
        job_id: str,
        report: Report,
        authorization: Annotated[Optional[str], Header()] = None,
    ) -> Response:
        auth(authorization)
        if report.job_id != job_id:
            raise _err(400, "report job_id does not match the URL")
        state.record_report(report)
        # Object-storage verification and the delete list land with the store
        # step; without a store there is nothing the bridge may delete.
        return Response(status_code=204)

    @r.put("/jobs/{job_id}/artifacts/{name}")
    async def put_artifact(
        job_id: str,
        name: str,
        request: Request,
        authorization: Annotated[Optional[str], Header()] = None,
    ) -> Response:
        auth(authorization)
        if not is_plain_name(name):
            raise _err(400, "artifact name must be a plain file name")
        data = await request.body()
        content_type = request.headers.get("content-type", "application/octet-stream")
        try:
            state.store_artifact(job_id, name, content_type, data)
        except GatewayError as e:
            raise _err(413 if e.code == "too_large" else 400, e.code)
        return Response(status_code=204)

    return r


def admin_router(state: GatewayState, settings) -> APIRouter:
    r = APIRouter(prefix="/v1/admin")

    def auth(authorization: Optional[str]) -> None:
        if authorization != f"Bearer {settings.admin_token}":
            raise _err(401, "unauthorized")

    @r.post("/bridges")
    def enroll(
        body: dict[str, Any],
        authorization: Annotated[Optional[str], Header()] = None,
    ) -> dict[str, Any]:
        auth(authorization)
        try:
            b = state.enroll_bridge(
                body["bridge"], body["token"], body.get("family", "hikvision"), body.get("tz", "")
            )
        except (KeyError, GatewayError) as e:
            raise _err(400, str(e))
        return {"bridge": b.id, "family": b.family, "tz": b.tz or settings.default_device_tz}

    @r.post("/jobs")
    def submit(
        body: dict[str, Any],
        authorization: Annotated[Optional[str], Header()] = None,
    ) -> dict[str, Any]:
        auth(authorization)
        try:
            job = Job.model_validate(body["job"])
            state.submit(job, body["bridge"])
        except KeyError as e:
            raise _err(400, f"missing {e}")
        except GatewayError as e:
            raise _err(409 if e.code == "duplicate_job" else 400, e.code)
        return {"job": job.id, "bridge": body["bridge"], "kind": job.kind}

    @r.get("/jobs/{job_id}/report")
    def get_report(job_id: str, authorization: Annotated[Optional[str], Header()] = None) -> dict[str, Any]:
        auth(authorization)
        rep = state.reports.get(job_id)
        if rep is None:
            raise _err(404, "no report yet")
        return rep.model_dump(exclude_none=True)

    @r.get("/audit")
    def get_audit(
        n: int = 50,
        authorization: Annotated[Optional[str], Header()] = None,
    ) -> list[dict[str, Any]]:
        auth(authorization)
        return state.audit.tail(n)

    return r
