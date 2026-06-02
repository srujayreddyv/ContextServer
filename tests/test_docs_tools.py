"""Unit tests for docs_tools: docs_search."""

import os

import pytest

from server.path_utils import PathContainmentError
from tools.docs_tools import (
    docs_search,
    make_docs_search_tool,
    set_repo_root,
)


@pytest.fixture
def docs_repo(tmp_path):
    """Set up a temporary repo root with documentation files."""
    set_repo_root(str(tmp_path))

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "guide.md").write_text(
        "# Guide\n\nContextServer explains repository context.\nMore details here.\n",
        encoding="utf-8",
    )
    (docs / "api.rst").write_text(
        "API Reference\n=============\n\nUse the MCP tools carefully.\n",
        encoding="utf-8",
    )
    (docs / "notes.txt").write_text(
        "alpha\nbeta\ngamma\ndelta\nepsilon\n",
        encoding="utf-8",
    )
    (docs / "script.py").write_text(
        "ContextServer should not be found here.\n",
        encoding="utf-8",
    )

    return tmp_path


@pytest.mark.asyncio
async def test_docs_search_finds_markdown_docs(docs_repo):
    result = await docs_search({"query": "ContextServer"})

    assert len(result) == 1
    assert result[0]["file"] == os.path.join("docs", "guide.md")
    assert result[0]["line_number"] == 3
    assert "repository context" in result[0]["content"]


@pytest.mark.asyncio
async def test_docs_search_uses_docs_dir_when_provided(tmp_path):
    set_repo_root(str(tmp_path))
    custom = tmp_path / "manuals"
    custom.mkdir()
    (custom / "setup.mdx").write_text(
        "# Setup\n\nInstall ContextServer locally.\n",
        encoding="utf-8",
    )
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "ignored.md").write_text("ContextServer default docs.\n", encoding="utf-8")

    result = await docs_search({"query": "install", "docs_dir": "manuals"})

    assert len(result) == 1
    assert result[0]["file"] == os.path.join("manuals", "setup.mdx")


@pytest.mark.asyncio
async def test_docs_search_defaults_to_data_docs_when_docs_absent(tmp_path):
    set_repo_root(str(tmp_path))
    data_docs = tmp_path / "data" / "docs"
    data_docs.mkdir(parents=True)
    (data_docs / "overview.md").write_text("ContextServer overview.\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("ContextServer root readme.\n", encoding="utf-8")

    result = await docs_search({"query": "ContextServer"})

    assert len(result) == 1
    assert result[0]["file"] == os.path.join("data", "docs", "overview.md")


@pytest.mark.asyncio
async def test_docs_search_falls_back_to_repo_root(tmp_path):
    set_repo_root(str(tmp_path))
    (tmp_path / "README.md").write_text("ContextServer root readme.\n", encoding="utf-8")

    result = await docs_search({"query": "ContextServer"})

    assert len(result) == 1
    assert result[0]["file"] == "README.md"


@pytest.mark.asyncio
async def test_docs_search_case_insensitive_by_default(docs_repo):
    result = await docs_search({"query": "contextserver"})

    assert len(result) == 1
    assert result[0]["file"] == os.path.join("docs", "guide.md")


@pytest.mark.asyncio
async def test_docs_search_honors_case_sensitive(docs_repo):
    result = await docs_search({"query": "contextserver", "case_sensitive": True})

    assert result == []


@pytest.mark.asyncio
async def test_docs_search_rejects_docs_dir_escape(tmp_path):
    set_repo_root(str(tmp_path))

    with pytest.raises(PathContainmentError):
        await docs_search({"query": "secret", "docs_dir": "../../etc"})


@pytest.mark.asyncio
async def test_docs_search_skips_non_doc_files(docs_repo):
    result = await docs_search({"query": "should not be found"})

    assert result == []


@pytest.mark.asyncio
async def test_docs_search_respects_max_results(docs_repo):
    result = await docs_search({"query": "a", "max_results": 2})

    assert len(result) == 2


@pytest.mark.asyncio
async def test_docs_search_returns_context(docs_repo):
    result = await docs_search({"query": "gamma"})

    assert len(result) == 1
    assert result[0]["context_before"] == ["alpha", "beta"]
    assert result[0]["context_after"] == ["delta", "epsilon"]


def test_make_docs_search_tool_returns_definition():
    tool = make_docs_search_tool()

    assert tool.name == "docs_search"
    assert "query" in tool.parameters["properties"]
    assert "max_results" in tool.parameters["properties"]
    assert tool.handler is docs_search
