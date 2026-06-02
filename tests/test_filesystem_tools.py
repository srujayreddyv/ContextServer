"""Unit tests for filesystem_tools: read_file and list_directory."""

import os

import pytest

from server.path_utils import PathContainmentError
from tools.filesystem_tools import (
    list_directory,
    make_list_directory_tool,
    make_read_file_tool,
    make_search_files_tool,
    read_file,
    search_files,
    set_repo_root,
)


@pytest.fixture
def repo(tmp_path):
    """Set up a temporary repo root with sample files."""
    set_repo_root(str(tmp_path))

    # Create a sample file with known content
    sample = tmp_path / "hello.txt"
    sample.write_text("line1\nline2\nline3\nline4\nline5\n", encoding="utf-8")

    # Create a subdirectory with a file
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "nested.txt").write_text("nested content\n", encoding="utf-8")

    return tmp_path


# --------------- full file read ---------------


@pytest.mark.asyncio
async def test_read_file_full_content(repo):
    result = await read_file({"path": "hello.txt"})
    assert result == "line1\nline2\nline3\nline4\nline5\n"


@pytest.mark.asyncio
async def test_read_file_nested(repo):
    result = await read_file({"path": "sub/nested.txt"})
    assert result == "nested content\n"


# --------------- line range slicing ---------------


@pytest.mark.asyncio
async def test_read_file_start_and_end_line(repo):
    result = await read_file({"path": "hello.txt", "start_line": 2, "end_line": 4})
    assert result == "line2\nline3\nline4\n"


@pytest.mark.asyncio
async def test_read_file_start_line_only(repo):
    result = await read_file({"path": "hello.txt", "start_line": 4})
    assert result == "line4\nline5\n"


@pytest.mark.asyncio
async def test_read_file_end_line_only(repo):
    result = await read_file({"path": "hello.txt", "end_line": 2})
    assert result == "line1\nline2\n"


@pytest.mark.asyncio
async def test_read_file_single_line(repo):
    result = await read_file({"path": "hello.txt", "start_line": 3, "end_line": 3})
    assert result == "line3\n"


# --------------- error cases ---------------


@pytest.mark.asyncio
async def test_read_file_not_found(repo):
    with pytest.raises(FileNotFoundError, match="no_such_file.txt"):
        await read_file({"path": "no_such_file.txt"})


@pytest.mark.asyncio
async def test_read_file_path_traversal(repo):
    with pytest.raises(PathContainmentError):
        await read_file({"path": "../../etc/passwd"})


# --------------- empty file ---------------


@pytest.mark.asyncio
async def test_read_file_empty(repo):
    (repo / "empty.txt").write_text("", encoding="utf-8")
    result = await read_file({"path": "empty.txt"})
    assert result == ""


# --------------- make_read_file_tool ---------------


def test_make_read_file_tool_returns_definition():
    tool = make_read_file_tool()
    assert tool.name == "read_file"
    assert "path" in tool.parameters["properties"]
    assert tool.handler is read_file


# =============== list_directory tests ===============


@pytest.fixture
def dir_repo(tmp_path):
    """Set up a temporary repo with a known directory structure."""
    set_repo_root(str(tmp_path))

    # root/
    #   file_a.txt
    #   sub/
    #     file_b.txt
    #     deep/
    #       file_c.txt
    (tmp_path / "file_a.txt").write_text("a", encoding="utf-8")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "file_b.txt").write_text("b", encoding="utf-8")
    deep = sub / "deep"
    deep.mkdir()
    (deep / "file_c.txt").write_text("c", encoding="utf-8")

    return tmp_path


# --------------- basic listing (depth=1) ---------------


@pytest.mark.asyncio
async def test_list_directory_root(dir_repo):
    result = await list_directory({"path": "."})
    names = {e["name"] for e in result}
    assert "file_a.txt" in names
    assert "sub" in names
    # depth=1 should NOT include nested entries
    assert not any("/" in e["name"] or "\\" in e["name"] for e in result)


@pytest.mark.asyncio
async def test_list_directory_types(dir_repo):
    result = await list_directory({"path": "."})
    type_map = {e["name"]: e["type"] for e in result}
    assert type_map["file_a.txt"] == "file"
    assert type_map["sub"] == "directory"


@pytest.mark.asyncio
async def test_list_directory_subdirectory(dir_repo):
    result = await list_directory({"path": "sub"})
    names = {e["name"] for e in result}
    assert "file_b.txt" in names
    assert "deep" in names


# --------------- recursive listing ---------------


@pytest.mark.asyncio
async def test_list_directory_depth_2(dir_repo):
    result = await list_directory({"path": ".", "depth": 2})
    names = {e["name"] for e in result}
    # depth=2 should include sub/file_b.txt and sub/deep
    assert os.path.join("sub", "file_b.txt") in names
    assert os.path.join("sub", "deep") in names
    # but NOT sub/deep/file_c.txt (that's depth 3)
    assert os.path.join("sub", "deep", "file_c.txt") not in names


@pytest.mark.asyncio
async def test_list_directory_depth_3(dir_repo):
    result = await list_directory({"path": ".", "depth": 3})
    names = {e["name"] for e in result}
    assert os.path.join("sub", "deep", "file_c.txt") in names


# --------------- empty directory ---------------


@pytest.mark.asyncio
async def test_list_directory_empty(dir_repo):
    empty = dir_repo / "empty_dir"
    empty.mkdir()
    result = await list_directory({"path": "empty_dir"})
    assert result == []


# --------------- error cases ---------------


@pytest.mark.asyncio
async def test_list_directory_not_found(dir_repo):
    with pytest.raises(FileNotFoundError, match="no_such_dir"):
        await list_directory({"path": "no_such_dir"})


@pytest.mark.asyncio
async def test_list_directory_path_traversal(dir_repo):
    with pytest.raises(PathContainmentError):
        await list_directory({"path": "../../etc"})


@pytest.mark.asyncio
async def test_list_directory_file_not_dir(dir_repo):
    """Passing a file path instead of a directory should raise FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        await list_directory({"path": "file_a.txt"})


# --------------- make_list_directory_tool ---------------


def test_make_list_directory_tool_returns_definition():
    tool = make_list_directory_tool()
    assert tool.name == "list_directory"
    assert "path" in tool.parameters["properties"]
    assert tool.handler is list_directory


# =============== search_files tests ===============


@pytest.fixture
def search_repo(tmp_path):
    """Set up a temporary repo with files for search testing."""
    set_repo_root(str(tmp_path))

    # root/
    #   app.py
    #   readme.md
    #   src/
    #     main.py
    #     utils.py
    #     data/
    #       config.json
    #       notes.txt
    (tmp_path / "app.py").write_text("print('app')", encoding="utf-8")
    (tmp_path / "readme.md").write_text("# Readme", encoding="utf-8")
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text("print('main')", encoding="utf-8")
    (src / "utils.py").write_text("print('utils')", encoding="utf-8")
    data = src / "data"
    data.mkdir()
    (data / "config.json").write_text("{}", encoding="utf-8")
    (data / "notes.txt").write_text("notes", encoding="utf-8")

    return tmp_path


# --------------- basic glob matching ---------------


@pytest.mark.asyncio
async def test_search_files_star_py(search_repo):
    """Glob *.py should match only top-level .py files."""
    result = await search_files({"pattern": "*.py"})
    assert "app.py" in result
    # *.py is non-recursive, should not match nested files
    assert all("src" not in r for r in result)


@pytest.mark.asyncio
async def test_search_files_recursive_py(search_repo):
    """Glob **/*.py should match all .py files recursively."""
    result = await search_files({"pattern": "**/*.py"})
    assert "app.py" in result
    assert os.path.join("src", "main.py") in result
    assert os.path.join("src", "utils.py") in result


@pytest.mark.asyncio
async def test_search_files_json(search_repo):
    """Glob **/*.json should find the config file."""
    result = await search_files({"pattern": "**/*.json"})
    assert os.path.join("src", "data", "config.json") in result
    assert len(result) == 1


# --------------- base_dir restriction ---------------


@pytest.mark.asyncio
async def test_search_files_with_base_dir(search_repo):
    """Searching within src/ should only return files under src/."""
    result = await search_files({"pattern": "*.py", "base_dir": "src"})
    assert os.path.join("src", "main.py") in result
    assert os.path.join("src", "utils.py") in result
    # Should not include top-level app.py
    assert "app.py" not in result


@pytest.mark.asyncio
async def test_search_files_base_dir_recursive(search_repo):
    """Recursive search within src/ should find nested files."""
    result = await search_files({"pattern": "**/*.txt", "base_dir": "src"})
    assert os.path.join("src", "data", "notes.txt") in result


# --------------- empty results ---------------


@pytest.mark.asyncio
async def test_search_files_no_matches(search_repo):
    """A pattern that matches nothing should return an empty list."""
    result = await search_files({"pattern": "*.xyz"})
    assert result == []


# --------------- path containment ---------------


@pytest.mark.asyncio
async def test_search_files_path_traversal(search_repo):
    """base_dir escaping the repo root should raise PathContainmentError."""
    with pytest.raises(PathContainmentError):
        await search_files({"pattern": "*.py", "base_dir": "../../etc"})


# --------------- results are sorted ---------------


@pytest.mark.asyncio
async def test_search_files_results_sorted(search_repo):
    """Results should be returned in sorted order."""
    result = await search_files({"pattern": "**/*.py"})
    assert result == sorted(result)


# --------------- make_search_files_tool ---------------


def test_make_search_files_tool_returns_definition():
    tool = make_search_files_tool()
    assert tool.name == "search_files"
    assert "pattern" in tool.parameters["properties"]
    assert tool.handler is search_files
