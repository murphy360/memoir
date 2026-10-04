"""The FastAPI application. Routers live in their own modules; this assembles them."""

from fastapi import FastAPI

from app import __version__
from app.accounts.csrf import OriginCheckMiddleware
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
from app.routers import auth, health, invitations, profile, users

ROUTERS = (health, auth, profile, users, invitations)
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
    questions,
    settings,
    merge,
    purge,
)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Memoir API", version=__version__, root_path=settings.root_path)
    app.add_middleware(OriginCheckMiddleware)
    app.add_middleware(RequestIdMiddleware)
    errors.install(app)
    for module in ROUTERS + DOMAIN:
        app.include_router(module.router)
    return app
