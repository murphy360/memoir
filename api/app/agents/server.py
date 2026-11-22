"""The MCP server: Memoir's tools over Streamable HTTP at /mcp, behind a bearer check.

Stateless: every request stands alone, so any API process can answer it. The bearer
token names a person through a grant (grants.caller); the tools then act as that person.
A viewer is not shown tell_story, and is refused it. Logs name the client and the tool,
never what was asked or told.
"""

import inspect
import logging
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Annotated

import anyio
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import Field
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import Receive, Scope, Send

from app import __version__
from app.accounts.models import User
from app.agents import grants, tools
from app.agents.oauth import resource_metadata_url
from app.core.audited import act_as
from app.core.db import session_factory
from app.core.errors import ApiError
from app.core.settings import get_settings

log = logging.getLogger(__name__)
INSTRUCTIONS = (
    "Memoir is a family's archive of told stories. You act as the person who signed "
    "in, with their role. Use search_memories and get_memory to find what someone "
    "said; timeline and list_people for the shape of a life. To save a story, call "
    "tell_story with the person's own words, as they said them: do not summarise or "
    "polish. next_question gives the interviewer's next question for them; pass its "
    "question_id to tell_story with the answer."
)
READING = ToolAnnotations(read_only_hint=True, open_world_hint=False)


@dataclass(frozen=True)
class Who:
    """The caller, as the bearer check found it."""

    user_id: int
    role: str
    client_id: str
    client_name: str


current: ContextVar[Who | None] = ContextVar("mcp_caller", default=None)


def _run(name: str, fn, *args, **kwargs):
    """Run a tool as the caller, in its own database session."""
    who = current.get()
    if who is None:
        raise ToolError("Not signed in.")
    if name not in tools.allowed(who.role):
        raise ToolError("Your role does not allow this.")
    log.info("mcp tool=%s client=%s", name, who.client_id)
    with session_factory()() as db:
        user = db.get(User, who.user_id)
        act_as(db, user.id)
        try:
            return fn(db, user, *args, **kwargs)
        except ApiError as exc:
            raise ToolError(exc.message) from exc


class MemoirServer(MCPServer):
    async def list_tools(self):
        """Only the tools the caller's role allows."""
        who = current.get()
        names = tools.allowed(who.role) if who else ()
        return [t for t in await super().list_tools() if t.name in names]


Cursor = Annotated[str | None, Field(description="next_cursor from the last page")]


def _tool(mcp: MemoirServer, annotations: ToolAnnotations = READING):
    """Register a function as a tool, its docstring (dedented) its description."""

    def register(fn):
        return mcp.tool(
            description=inspect.cleandoc(fn.__doc__), annotations=annotations
        )(fn)

    return register


def build() -> MemoirServer:
    mcp = MemoirServer(
        "memoir", title="Memoir", instructions=INSTRUCTIONS, version=__version__
    )

    @_tool(mcp)
    def whoami() -> dict:
        """Who you are acting as: name, role, archive, and the tools that role allows."""
        return _run("whoami", tools.whoami, current.get().client_name)

    @_tool(mcp)
    def search_memories(
        query: Annotated[
            str | None, Field(description="Words in the title, summary or words")
        ] = None,
        person_id: Annotated[
            int | None, Field(description="Told by or mentioning this person")
        ] = None,
        date_from: Annotated[
            str | None, Field(description="On or after, e.g. 1968 or summer 1972")
        ] = None,
        date_to: Annotated[str | None, Field(description="On or before")] = None,
        cursor: Cursor = None,
        limit: Annotated[int, Field(ge=1, le=50)] = 20,
    ) -> dict:
        """Find stories by their words, a person, or when they happened. Only stories
        the signed-in person may see. Read one in full with get_memory."""
        return _run(
            "search_memories",
            tools.search_memories,
            query,
            person_id,
            date_from,
            date_to,
            cursor,
            limit,
        )

    @_tool(mcp)
    def get_memory(memory_id: int) -> dict:
        """One story: its words, dates, people, places and where it is filed."""
        return _run("get_memory", tools.get_memory, memory_id)

    @_tool(mcp)
    def timeline(
        person_id: Annotated[
            int | None, Field(description="Whose life; leave out for your own")
        ] = None,
        cursor: Cursor = None,
    ) -> dict:
        """A person's periods (chapters of their life) in order, with their events."""
        return _run("timeline", tools.timeline, person_id, cursor)

    @_tool(mcp)
    def list_people(
        query: Annotated[
            str | None, Field(description="Name or alias contains")
        ] = None,
        cursor: Cursor = None,
        limit: Annotated[int, Field(ge=1, le=50)] = 50,
    ) -> dict:
        """The people in the archive, by name."""
        return _run("list_people", tools.list_people, query, cursor, limit)

    @_tool(mcp)
    def next_question() -> dict:
        """The interviewer's next question for the signed-in person, or none."""
        return _run("next_question", tools.next_question)

    @_tool(mcp, ToolAnnotations(destructive_hint=False, open_world_hint=False))
    def tell_story(
        story: Annotated[
            str, Field(description="The story in the person's own words, as told")
        ],
        title: Annotated[str | None, Field(description="A short title")] = None,
        date: Annotated[
            str | None,
            Field(description="When it happened, as they said it: 1968, summer 1972"),
        ] = None,
        question_id: Annotated[
            int | None, Field(description="The question it answers (next_question)")
        ] = None,
    ) -> dict:
        """Save a story the signed-in person told you, as theirs. Memoir files it on
        their timeline by itself, like a story recorded in the app, and marks it as
        told through you."""
        return _run(
            "tell_story",
            tools.tell_story,
            current.get().client_name,
            story,
            title,
            date,
            question_id,
        )

    return mcp


def _who(raw: str | None) -> Who | None:
    with session_factory()() as db:
        found = grants.caller(db, raw)
        if found is None:
            return None
        return Who(
            found.user.id,
            found.user.role,
            found.client.client_id,
            found.client.client_name,
        )


def unauthorized(error: str | None) -> JSONResponse:
    challenge = f'Bearer resource_metadata="{resource_metadata_url(get_settings())}"'
    if error:
        challenge += f', error="{error}"'
    body = {
        "error": {"code": "unauthenticated", "message": "Connect again.", "field": None}
    }
    return JSONResponse(body, 401, headers={"WWW-Authenticate": challenge})


class Endpoint:
    """The ASGI app at /mcp: the bearer check, then the SDK's transport."""

    def __init__(self, mcp: MemoirServer):
        mcp.streamable_http_app(
            stateless_http=True,
            json_response=True,
            # The proxy and the bearer token guard this route; no cookie is used here.
            transport_security=TransportSecuritySettings(
                enable_dns_rebinding_protection=False
            ),
        )
        self.manager = mcp.session_manager

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        header = Headers(scope=scope).get("authorization", "")
        raw = header[7:].strip() if header.lower().startswith("bearer ") else None
        who = await anyio.to_thread.run_sync(_who, raw) if raw else None
        if who is None:
            await unauthorized("invalid_token" if raw else None)(scope, receive, send)
            return
        token = current.set(who)
        try:
            await self.manager.handle_request(scope, receive, send)
        finally:
            current.reset(token)
