"""Tests for the local MCP web UI helpers and API."""

import os

import pytest

from server.web_ui import (
    _add_user_server,
    _builtin_context_server,
    _delete_user_server,
    _list_tools,
    _load_servers,
    _normalize_args,
    _normalize_server,
    _read_user_servers,
    _write_user_servers,
)


def test_normalize_args_from_shell_string():
    assert _normalize_args("-m server.main --repo-root .") == [
        "-m",
        "server.main",
        "--repo-root",
        ".",
    ]


def test_normalize_server_generates_config():
    config = _normalize_server(
        {
            "name": "Example MCP",
            "command": "python",
            "args": "-m example",
            "cwd": "/tmp/example",
        }
    )

    assert config["id"].startswith("example-mcp-")
    assert config["name"] == "Example MCP"
    assert config["command"] == "python"
    assert config["args"] == ["-m", "example"]
    assert config["cwd"] == "/tmp/example"
    assert config["builtin"] is False


def test_read_write_user_servers(tmp_path):
    config_path = str(tmp_path / "servers.json")
    servers = [_normalize_server({"name": "Example", "command": "python"})]

    _write_user_servers(config_path, servers)

    assert _read_user_servers(config_path) == servers


def test_load_servers_includes_builtin_contextserver(tmp_path):
    config_path = str(tmp_path / "missing.json")

    servers = _load_servers(config_path, str(tmp_path))

    assert servers[0]["id"] == "contextserver"
    assert servers[0]["builtin"] is True


def test_builtin_contextserver_uses_repo_root(tmp_path):
    server = _builtin_context_server(str(tmp_path))

    assert server["args"][-1] == str(tmp_path)
    assert server["cwd"]


def test_add_load_and_delete_user_server(tmp_path):
    config_path = str(tmp_path / "servers.json")
    server = _add_user_server(
        config_path,
        {
            "name": "Example",
            "command": "python",
            "args": "-m example",
        },
    )

    servers = _load_servers(config_path, str(tmp_path))
    assert {entry["id"] for entry in servers} == {"contextserver", server["id"]}

    assert _delete_user_server(config_path, server["id"]) is True
    assert _delete_user_server(config_path, server["id"]) is False


@pytest.mark.asyncio
async def test_list_tools_for_builtin_contextserver(tmp_path):
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    os.makedirs(tmp_path / "data" / "docs")
    (tmp_path / "data" / "docs" / "guide.md").write_text(
        "ContextServer docs.\n",
        encoding="utf-8",
    )
    server = _builtin_context_server(str(tmp_path))

    tools = await _list_tools(server)

    names = {tool["name"] for tool in tools}
    assert "read_file" in names
    assert "docs_search" in names
