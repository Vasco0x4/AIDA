"""
HTTP MCP integration — mounts the Streamable-HTTP transport on the FastAPI
backend at ``/mcp``.

Uses ``StreamableHTTPSessionManager`` in stateless mode: a fresh transport
per request with no session tracking. This keeps auth/DB plumbing simple
(no sticky sessions to match against API keys) and is a good fit for the
low request rate of a single AI client.

Lifecycle — the session manager requires its ``run()`` context to be active
while handling requests. ``mcp_lifespan`` exposes an async context manager
that the FastAPI ``lifespan`` function chains with its own startup code.
"""
from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from starlette.requests import Request

# ``backend/mcp/`` is intentionally not a Python package (no ``__init__.py``)
# because a package named ``mcp`` would collide with the installed MCP SDK.
# Put its loose modules on sys.path so they resolve as top-level imports.
_BACKEND_DIR = Path(__file__).parent
_MCP_DIR = _BACKEND_DIR / "mcp"
_MODULES_DIR = _MCP_DIR / "modules"
for _p in (str(_MODULES_DIR), str(_MCP_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from mcp.server.streamable_http_manager import StreamableHTTPSessionManager  # noqa: E402
from starlette.responses import Response  # noqa: E402

from mcp_classes import AidaMCPService  # noqa: E402
from server_builder import build_mcp_server  # noqa: E402


class _AlreadySentResponse(Response):
    """No-op response used when the MCP session manager has already driven
    the ASGI protocol itself. Prevents Starlette from emitting a second
    ``http.response.start`` message on top of ours.
    """

    def __init__(self) -> None:
        super().__init__(content=b"", status_code=200)

    async def __call__(self, scope, receive, send) -> None:  # type: ignore[override]
        return None


_mcp_service: AidaMCPService | None = None
_session_manager: StreamableHTTPSessionManager | None = None


def get_session_manager() -> StreamableHTTPSessionManager:
    """Lazily construct the session manager + MCP server.

    Safe to call multiple times; only the first invocation does work.
    """
    global _mcp_service, _session_manager
    if _session_manager is not None:
        return _session_manager

    _mcp_service = AidaMCPService()
    server = build_mcp_server(_mcp_service)
    # Stateful mode — the manager issues an ``Mcp-Session-Id`` on initialize
    # and clients (OpenWebUI, Claude Desktop, Cursor) echo it on subsequent
    # requests. Stateless mode breaks clients that keep a session between
    # ``initialize`` and ``tools/list``.
    _session_manager = StreamableHTTPSessionManager(
        app=server,
        event_store=None,
        json_response=False,
        stateless=False,
    )
    return _session_manager


@asynccontextmanager
async def mcp_lifespan() -> AsyncIterator[None]:
    """Initialise the MCP service + run the session-manager task group.

    Intended to be composed inside the FastAPI app's own lifespan.
    """
    manager = get_session_manager()
    assert _mcp_service is not None  # set by get_session_manager

    await _mcp_service.initialize()
    try:
        async with manager.run():
            yield
    finally:
        await _mcp_service.cleanup()


async def handle_mcp_request(request: Request) -> Response:
    """Forward the request to the session manager and return a no-op Response.

    The session manager uses the raw ASGI ``send`` callable to emit its own
    response, so we return a sentinel that suppresses Starlette's own send.
    """
    manager = get_session_manager()
    await manager.handle_request(request.scope, request.receive, request._send)
    return _AlreadySentResponse()
