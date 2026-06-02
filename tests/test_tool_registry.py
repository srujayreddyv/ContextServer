"""Unit tests for tool_registry module."""

import pytest

from server.tool_registry import (
    InvalidParametersError,
    ToolDefinition,
    ToolNotFoundError,
    ToolRegistry,
)


# --------------- helpers ---------------

async def _echo_handler(params):
    """Simple handler that echoes params back."""
    return params


def _make_tool(name: str = "echo", description: str = "Echo tool") -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=description,
        parameters={
            "type": "object",
            "properties": {
                "message": {"type": "string"},
            },
            "required": ["message"],
        },
        handler=_echo_handler,
    )


# --------------- register / manifest ---------------

def test_register_and_manifest():
    registry = ToolRegistry()
    tool = _make_tool()
    registry.register(tool)

    manifest = registry.get_manifest()
    assert len(manifest) == 1
    assert manifest[0]["name"] == "echo"
    assert manifest[0]["description"] == "Echo tool"
    assert "properties" in manifest[0]["parameters"]


def test_manifest_empty_registry():
    registry = ToolRegistry()
    assert registry.get_manifest() == []


def test_register_multiple_tools():
    registry = ToolRegistry()
    registry.register(_make_tool("a", "Tool A"))
    registry.register(_make_tool("b", "Tool B"))

    manifest = registry.get_manifest()
    names = {entry["name"] for entry in manifest}
    assert names == {"a", "b"}


# --------------- call ---------------

@pytest.mark.asyncio
async def test_call_dispatches_to_handler():
    registry = ToolRegistry()
    registry.register(_make_tool())

    result = await registry.call("echo", {"message": "hello"})
    assert result == {"message": "hello"}


@pytest.mark.asyncio
async def test_call_unknown_tool_raises():
    registry = ToolRegistry()
    with pytest.raises(ToolNotFoundError, match="no_such_tool"):
        await registry.call("no_such_tool", {})


@pytest.mark.asyncio
async def test_call_invalid_params_raises():
    registry = ToolRegistry()
    registry.register(_make_tool())

    # "message" is required but missing
    with pytest.raises(InvalidParametersError):
        await registry.call("echo", {})


@pytest.mark.asyncio
async def test_call_wrong_param_type_raises():
    registry = ToolRegistry()
    registry.register(_make_tool())

    # "message" should be a string, not an int
    with pytest.raises(InvalidParametersError):
        await registry.call("echo", {"message": 42})
