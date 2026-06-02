"""Tests for internal tool plugin registration."""

import pytest

from server.tool_registry import InvalidParametersError, ToolRegistry
from tool_plugins import register_all


def test_register_all_loads_expected_tools(tmp_path):
    registry = ToolRegistry()
    register_all(registry, str(tmp_path))

    manifest = registry.get_manifest()
    names = {entry["name"] for entry in manifest}

    assert names == {
        "read_file",
        "list_directory",
        "search_files",
        "git_log",
        "git_diff",
        "git_status",
        "git_branches",
        "grep_search",
        "docs_search",
    }


def test_docs_search_appears_in_manifest(tmp_path):
    registry = ToolRegistry()
    register_all(registry, str(tmp_path))

    manifest = registry.get_manifest()
    docs_entry = [entry for entry in manifest if entry["name"] == "docs_search"][0]

    assert "documentation-like files" in docs_entry["description"]
    assert "query" in docs_entry["parameters"]["properties"]


@pytest.mark.asyncio
async def test_registered_tools_still_validate_params(tmp_path):
    registry = ToolRegistry()
    register_all(registry, str(tmp_path))

    with pytest.raises(InvalidParametersError):
        await registry.call("docs_search", {})
