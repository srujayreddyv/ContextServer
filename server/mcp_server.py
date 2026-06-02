"""MCP protocol handling (initialize, tools/list, tools/call).

Wraps the ``mcp`` Python SDK's low-level ``Server`` to expose the
ContextServer's tool registry over MCP.  The SDK handles the
initialize/initialized handshake automatically; this module registers
``list_tools`` and ``call_tool`` handlers that delegate to the
:class:`~server.tool_registry.ToolRegistry`.
"""

import json
import logging
import sys

from mcp import types
from mcp.server.lowlevel import Server, NotificationOptions
from mcp.server.stdio import stdio_server

from server.path_utils import PathContainmentError
from server.tool_registry import (
    InvalidParametersError,
    ToolNotFoundError,
    ToolRegistry,
)

logger = logging.getLogger(__name__)

# Exception types from tool modules that should be converted to
# user-facing MCP error responses rather than crashing the server.
_TOOL_ERROR_TYPES = (
    ToolNotFoundError,
    InvalidParametersError,
    PathContainmentError,
    FileNotFoundError,
)

# Lazy imports for git error types — they live in the tools layer and
# may not always be importable (e.g. in minimal test setups).
try:
    from tools.git_tools import GitNotAvailableError, GitRefNotFoundError

    _TOOL_ERROR_TYPES = (  # type: ignore[assignment]
        *_TOOL_ERROR_TYPES,
        GitNotAvailableError,
        GitRefNotFoundError,
    )
except ImportError:
    pass


class ContextMCPServer:
    """Thin wrapper around the ``mcp`` SDK ``Server``.

    Registers ``list_tools`` and ``call_tool`` handlers that delegate
    to a :class:`ToolRegistry`, converting known exceptions into MCP
    error responses.

    Args:
        registry: The tool registry containing all registered tools.
        repo_root: Absolute path to the repository root directory.
        transport: Transport type — ``"stdio"`` (default) or ``"sse"``.
    """

    def __init__(
        self,
        registry: ToolRegistry,
        repo_root: str,
        transport: str = "stdio",
    ) -> None:
        self._registry = registry
        self._repo_root = repo_root
        self._transport = transport

        self._server = Server(
            name="ContextServer",
            version="0.1.0",
        )

        self._register_handlers()

    # ------------------------------------------------------------------
    # Handler registration
    # ------------------------------------------------------------------

    def _register_handlers(self) -> None:
        """Wire MCP request handlers to the tool registry."""

        @self._server.list_tools()
        async def _list_tools() -> list[types.Tool]:
            manifest = self._registry.get_manifest()
            return [
                types.Tool(
                    name=entry["name"],
                    description=entry.get("description", ""),
                    inputSchema=entry.get("parameters", {"type": "object"}),
                )
                for entry in manifest
            ]

        @self._server.call_tool()
        async def _call_tool(
            name: str, arguments: dict
        ) -> types.CallToolResult:
            try:
                result = await self._registry.call(name, arguments)
                # Normalise the result into MCP TextContent
                if isinstance(result, str):
                    text = result
                else:
                    text = json.dumps(result, default=str)

                return types.CallToolResult(
                    content=[types.TextContent(type="text", text=text)],
                    isError=False,
                )
            except _TOOL_ERROR_TYPES as exc:
                error_msg = f"{type(exc).__name__}: {exc}"
                logger.warning("Tool call %s failed: %s", name, error_msg)
                return types.CallToolResult(
                    content=[
                        types.TextContent(type="text", text=error_msg)
                    ],
                    isError=True,
                )
            except Exception as exc:
                error_msg = f"Internal error: {exc}"
                logger.exception("Unexpected error in tool %s", name)
                return types.CallToolResult(
                    content=[
                        types.TextContent(type="text", text=error_msg)
                    ],
                    isError=True,
                )

    # ------------------------------------------------------------------
    # Server lifecycle
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Start the MCP server on the configured transport.

        Currently supports ``"stdio"``.  SSE support can be added by
        wiring ``SseServerTransport`` from the ``mcp`` SDK.
        """
        if self._transport == "stdio":
            await self._run_stdio()
        else:
            raise ValueError(f"Unsupported transport: {self._transport}")

    async def _run_stdio(self) -> None:
        """Run the server over stdio transport."""
        init_options = self._server.create_initialization_options(
            notification_options=NotificationOptions(),
        )
        async with stdio_server() as (read_stream, write_stream):
            await self._server.run(
                read_stream,
                write_stream,
                init_options,
            )
