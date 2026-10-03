"""The FastAPI application. Routers live in their own modules; this assembles them."""

from fastapi import FastAPI

from app import __version__
from app.accounts.csrf import OriginCheckMiddleware
from app.core import errors
from app.core.logging import RequestIdMiddleware
from app.core.settings import get_settings
from app.routers import auth, health, invitations, profile, users

ROUTERS = (health, auth, profile, users, invitations)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Memoir API", version=__version__, root_path=settings.root_path)
    app.add_middleware(OriginCheckMiddleware)
    app.add_middleware(RequestIdMiddleware)
    errors.install(app)
    for module in ROUTERS:
        app.include_router(module.router)
    return app
