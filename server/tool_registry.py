"""Tool registration, manifest generation, and dispatch.

The ToolRegistry manages tool definitions and handles dispatching
tool calls with parameter validation against JSON Schema.
"""

from dataclasses import dataclass
from typing import Any, Callable

import jsonschema


class ToolNotFoundError(Exception):
    """Raised when a tools/call request references an unknown tool name."""


class InvalidParametersError(Exception):
    """Raised when parameters fail JSON Schema validation."""


@dataclass
class ToolDefinition:
    """Describes a single tool exposed by the server.

    Attributes:
        name: Unique tool identifier.
        description: Human-readable description of what the tool does.
        parameters: JSON Schema dict describing accepted parameters.
        handler: Async callable ``(params, repo_root) -> result``.
    """

    name: str
    description: str
    parameters: dict
    handler: Callable  # async function(params, repo_root) -> result


class ToolRegistry:
    """Stores tool definitions and dispatches calls."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        """Register a tool definition.

        Args:
            tool: The tool to register.
        """
        self._tools[tool.name] = tool

    def get_manifest(self) -> list[dict]:
        """Return the tool manifest for ``tools/list``.

        Each entry contains the tool's name, description, and
        parameter schema — everything an MCP client needs for
        discovery.
        """
        return [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            }
            for t in self._tools.values()
        ]

    async def call(self, name: str, params: dict) -> Any:
        """Validate and dispatch a tool call.

        Args:
            name: The tool name to invoke.
            params: Parameters to pass to the tool handler.

        Returns:
            The result produced by the tool handler.

        Raises:
            ToolNotFoundError: If *name* is not registered.
            InvalidParametersError: If *params* violate the tool's
                JSON Schema.
        """
        tool = self._tools.get(name)
        if tool is None:
            raise ToolNotFoundError(f"Unknown tool: {name}")

        try:
            jsonschema.validate(instance=params, schema=tool.parameters)
        except jsonschema.ValidationError as exc:
            raise InvalidParametersError(str(exc.message)) from exc

        return await tool.handler(params)
