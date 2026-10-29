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

    if settings.store == "r2":
        from .objectstore import R2Store

        state.objectstore = R2Store(settings.r2)
    elif settings.store == "local":
        from .objectstore import LocalStore

        store = LocalStore(secret=settings.local_store_secret, base_url=settings.local_store_base)
        state.objectstore = store
        app.include_router(store.router())

    # The MCP server is attached in the tools step.
    app.state.gateway = state
    app.state.settings = settings
    return app


app = create_app  # uvicorn --factory
