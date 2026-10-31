"""python -m rikuy_gateway: serve bridges (REST) and agents (MCP) in one process."""

from __future__ import annotations

import uvicorn

from .app import create_app
from .config import Settings


def main() -> None:
    settings = Settings.from_env()
    settings.ensure_dirs()
    uvicorn.run(create_app(settings), host="127.0.0.1", port=8000, log_level="info")


if __name__ == "__main__":
    main()
