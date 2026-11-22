"""The FastAPI application. Routers live in their own modules; this assembles them."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.routing import Route

from app import __version__
from app.accounts.csrf import OriginCheckMiddleware
from app.agents import oauth, server
from app.agents import router as agents
from app.agents.grants import OAuthError
from app.analysis import router as analysis
from app.capture import router as capture
from app.core import errors
from app.core.logging import RequestIdMiddleware
from app.core.settings import get_settings
from app.dates import router as dates
from app.domain import (
    assets,
    epics,
    events,
    memories,
    merge,
    participants,
    people,
    periods,
    places,
    purge,
    questions,
    settings,
    threads,
)
from app.placement import router as placement
from app.questions import router as interviewer
from app.routers import auth, health, invitations, profile, users

ROUTERS = (health, auth, profile, agents, users, invitations, oauth)
DOMAIN = (
    analysis,
    capture,
    dates,
    people,
    places,
    threads,
    periods,
    epics,
    events,
    participants,
    placement,
    memories,
    assets,
    interviewer,
    questions,
    settings,
    merge,
    purge,
)


def create_app() -> FastAPI:
    settings = get_settings()
    mcp = server.Endpoint(server.build())

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        async with mcp.manager.run():
            yield

    app = FastAPI(
        title="Memoir API",
        version=__version__,
        root_path=settings.root_path,
        lifespan=lifespan,
    )
    app.add_middleware(OriginCheckMiddleware)
    app.add_middleware(RequestIdMiddleware)
    errors.install(app)
    app.add_exception_handler(OAuthError, oauth.error_response)
    for module in ROUTERS + DOMAIN:
        app.include_router(module.router)
    app.include_router(oauth.well_known(settings))
    # The MCP server (docs/AGENTS_MCP.md): an ASGI app of the SDK's, behind a bearer check.
    app.router.routes.append(Route("/mcp", mcp, include_in_schema=False))
    return app
