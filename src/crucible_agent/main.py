"""FastAPI エントリポイント"""

import logging

from fastapi import FastAPI

from crucible_agent import __version__
from crucible_agent.api.routes import router
from crucible_agent.config import settings

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(
    title="Crucible Agent",
    description="AI agent runtime connecting frontends to MCP servers via LLM",
    version=__version__,
)

app.include_router(router)
