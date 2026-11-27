"""
Shared MCP server builder.

Creates a low-level ``Server("aida-mcp")`` and registers its tools / resources.
Used by both the stdio entry point (``aida_mcp_server.py``) and the HTTP mount
(``mcp_http_app.py``) so both transports expose the same surface.
"""
from typing import Callable, Optional

from mcp.server import Server
from mcp.types import Tool, TextContent, Resource

# Resolve imports whether this module is loaded from the backend root or
# through the ``backend.mcp`` package path.
import os
import sys

_MODULES_DIR = os.path.join(os.path.dirname(__file__), "modules")
if _MODULES_DIR not in sys.path:
    sys.path.insert(0, _MODULES_DIR)

from mcp_tools import get_tool_definitions  # noqa: E402
from mcp_handlers import handle_tool_call  # noqa: E402
from mcp_resources import get_resources, handle_resource_read  # noqa: E402

# Tools hidden from clients bound to a single assessment (agent keys).
_UNBOUND_ONLY_TOOLS = {"create_assessment"}


def build_mcp_server(mcp_service=None, *, service_for_request: Optional[Callable] = None) -> Server:
    """Build a low-level MCP Server with tools and resources wired up.

    Pass either:

    - ``mcp_service``: the single ``AidaMCPService`` every call uses (stdio:
      one process per client). The caller must ``await initialize()`` it.
    - ``service_for_request``: called with the MCP request context on every
      call and returns the service of the client making it (HTTP: one
      service per API key, so clients never share a loaded assessment or a
      backend token).
    """
    if (mcp_service is None) == (service_for_request is None):
        raise ValueError("pass exactly one of mcp_service / service_for_request")

    server = Server("aida-mcp")

    def current_service():
        if service_for_request is None:
            return mcp_service
        return service_for_request(server.request_context)

    @server.list_resources()
    async def _list_resources() -> list[Resource]:
        return get_resources()

    @server.read_resource()
    async def _read_resource(uri: str) -> str:
        return await handle_resource_read(str(uri), current_service())

    @server.list_tools()
    async def _list_tools() -> list[Tool]:
        tools = get_tool_definitions()
        if getattr(current_service(), "pinned_assessment_id", None) is not None:
            tools = [t for t in tools if t.name not in _UNBOUND_ONLY_TOOLS]
        return tools

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict) -> list[TextContent]:
        return await handle_tool_call(name, arguments, current_service())

    return server
