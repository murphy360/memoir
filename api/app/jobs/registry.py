"""What each kind of job does. Modules register handlers with `@handler("kind")`."""

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.jobs import queue


@dataclass
class JobContext:
    """What a handler gets besides its payload: a way to report progress."""

    session: Session
    job_id: int

    def progress(self, **values) -> None:
        queue.beat(self.session, self.job_id, progress=values)


Handler = Callable[[JobContext, dict], dict | None]
HANDLERS: dict[str, Handler] = {}


class PermanentError(Exception):
    """Raise from a handler when retrying cannot help (bad payload, missing record)."""


def handler(kind: str) -> Callable[[Handler], Handler]:
    def register(fn: Handler) -> Handler:
        HANDLERS[kind] = fn
        return fn

    return register


@handler("system.ping")
def ping(ctx: JobContext, payload: dict) -> dict:
    """A job that proves the worker runs: it echoes its payload."""
    ctx.progress(step="pong")
    return {"pong": payload}
