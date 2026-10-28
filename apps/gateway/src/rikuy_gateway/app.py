"""Application factory: one process serves bridges (REST) and agents (MCP).

    uvicorn rikuy_gateway.app:app --factory
"""

from __future__ import annotations

from fastapi import FastAPI

from .audit import AuditLog
from .bridge_api import admin_router, bridge_router
from .config import Settings
from .state import GatewayState


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.dev()
    settings.ensure_dirs()
    audit = AuditLog(settings.audit_path)
    state = GatewayState(settings, audit)

    app = FastAPI(title="rikuy-gateway", version="0.1.0")
    app.include_router(bridge_router(state, settings))
    app.include_router(admin_router(state, settings))

    # Object storage (step 3) and the MCP server (step 4) attach here next.
    app.state.gateway = state
    app.state.settings = settings
    return app


app = create_app  # uvicorn --factory
