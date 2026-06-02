"""Unit tests for search_tools: grep_search."""

import os

import pytest

from tools.search_tools import (
    grep_search,
    make_grep_search_tool,
    set_repo_root,
)


@pytest.fixture
def repo(tmp_path):
    """Set up a temporary repo root with sample files for grep testing."""
    set_repo_root(str(tmp_path))

    # hello.py — a small Python file
    (tmp_path / "hello.py").write_text(
        "# greeting module\ndef greet(name):\n    return f'Hello, {name}!'\n\nprint(greet('World'))\n",
        encoding="utf-8",
    )

    # readme.md — a markdown file
    (tmp_path / "readme.md").write_text(
        "# Project\n\nThis is a sample project.\nIt contains Hello World code.\n",
        encoding="utf-8",
    )

    # sub/data.txt — nested file
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "data.txt").write_text(
        "alpha\nbeta\ngamma\ndelta\nepsilon\n",
        encoding="utf-8",
    )

    return tmp_path


# --------------- basic search ---------------


@pytest.mark.asyncio
async def test_grep_basic_match(repo):
    """A simple query should find matching lines."""
    result = await grep_search({"query": "greet"})
    assert len(result) >= 1
    files = {m["file"] for m in result}
    assert "hello.py" in files


@pytest.mark.asyncio
async def test_grep_returns_correct_line_number(repo):
    """Line numbers should be 1-indexed and accurate."""
    result = await grep_search({"query": "def greet"})
    match = [m for m in result if m["file"] == "hello.py"][0]
    assert match["line_number"] == 2
    assert "def greet" in match["content"]


@pytest.mark.asyncio
async def test_grep_returns_context_lines(repo):
    """Each match should include up to 2 lines of context before and after."""
    result = await grep_search({"query": "gamma"})
    match = [m for m in result if m["file"] == os.path.join("sub", "data.txt")][0]
    # gamma is line 3 (1-indexed); context_before = [alpha, beta]
    assert match["context_before"] == ["alpha", "beta"]
    # context_after = [delta, epsilon]
    assert match["context_after"] == ["delta", "epsilon"]


@pytest.mark.asyncio
async def test_grep_context_at_file_start(repo):
    """Matches near the start of a file should have truncated context_before."""
    result = await grep_search({"query": "alpha"})
    match = [m for m in result if m["file"] == os.path.join("sub", "data.txt")][0]
    assert match["context_before"] == []
    assert len(match["context_after"]) == 2


@pytest.mark.asyncio
async def test_grep_context_at_file_end(repo):
    """Matches near the end of a file should have truncated context_after."""
    result = await grep_search({"query": "epsilon"})
    match = [m for m in result if m["file"] == os.path.join("sub", "data.txt")][0]
    assert len(match["context_before"]) == 2
    assert match["context_after"] == []


# --------------- include_pattern filtering ---------------


@pytest.mark.asyncio
async def test_grep_include_pattern_py(repo):
    """include_pattern should restrict results to matching files."""
    result = await grep_search({"query": "Hello", "include_pattern": "*.py"})
    files = {m["file"] for m in result}
    assert all(f.endswith(".py") for f in files)


@pytest.mark.asyncio
async def test_grep_include_pattern_excludes(repo):
    """Files not matching include_pattern should be excluded."""
    result = await grep_search({"query": "Hello", "include_pattern": "*.md"})
    files = {m["file"] for m in result}
    assert "hello.py" not in files
    assert "readme.md" in files


# --------------- case sensitivity ---------------


@pytest.mark.asyncio
async def test_grep_case_sensitive_default(repo):
    """Default search is case-sensitive; 'hello' should not match 'Hello'."""
    result = await grep_search({"query": "hello"})
    # "hello" (lowercase) appears in filename hello.py content only as "Hello"
    # The file hello.py has 'Hello' (capital H) in the f-string
    # readme.md has 'Hello World'
    # Neither should match lowercase 'hello' in case-sensitive mode
    for m in result:
        assert "hello" in m["content"].lower()
        # Verify the exact lowercase 'hello' is present
        assert "hello" in m["content"]


@pytest.mark.asyncio
async def test_grep_case_insensitive(repo):
    """case_sensitive=false should match regardless of case."""
    result = await grep_search({"query": "hello", "case_sensitive": False})
    files = {m["file"] for m in result}
    # Should find 'Hello' in both hello.py and readme.md
    assert "hello.py" in files
    assert "readme.md" in files


@pytest.mark.asyncio
async def test_grep_case_sensitive_no_match(repo):
    """Case-sensitive search for wrong case should return no matches."""
    result = await grep_search({"query": "GAMMA"})
    assert result == []


@pytest.mark.asyncio
async def test_grep_case_insensitive_match(repo):
    """Case-insensitive search should find differently-cased text."""
    result = await grep_search({"query": "GAMMA", "case_sensitive": False})
    assert len(result) == 1
    assert result[0]["content"] == "gamma"


# --------------- no matches ---------------


@pytest.mark.asyncio
async def test_grep_no_matches(repo):
    """A query that matches nothing should return an empty list."""
    result = await grep_search({"query": "zzz_nonexistent_zzz"})
    assert result == []


# --------------- empty repo ---------------


@pytest.mark.asyncio
async def test_grep_empty_repo(tmp_path):
    """Searching an empty repo should return an empty list."""
    set_repo_root(str(tmp_path))
    result = await grep_search({"query": "anything"})
    assert result == []


# --------------- binary file handling ---------------


@pytest.mark.asyncio
async def test_grep_skips_binary_files(repo):
    """Binary files that can't be decoded as UTF-8 should be skipped."""
    (repo / "binary.bin").write_bytes(b"\x80\x81\x82\x83")
    result = await grep_search({"query": "greet"})
    files = {m["file"] for m in result}
    assert "binary.bin" not in files


# --------------- make_grep_search_tool ---------------


def test_make_grep_search_tool_returns_definition():
    tool = make_grep_search_tool()
    assert tool.name == "grep_search"
    assert "query" in tool.parameters["properties"]
    assert tool.handler is grep_search
