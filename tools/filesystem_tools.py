"""Filesystem tools: read_file, list_directory, search_files.

All file operations go through ``resolve_and_validate()`` to ensure
paths stay within the configured repository root.
"""

import os
from pathlib import Path

from server.path_utils import resolve_and_validate
from server.tool_registry import ToolDefinition

# Module-level repo root, set via ``set_repo_root()`` before tool use.
_repo_root: str = ""


def set_repo_root(repo_root: str) -> None:
    """Configure the repository root used by all filesystem tools."""
    global _repo_root
    _repo_root = repo_root


async def read_file(params: dict) -> str:
    """Read file content, optionally slicing to a line range.

    Args:
        params: Dict with keys:
            - ``path`` (str): Relative file path within the repository.
            - ``start_line`` (int, optional): 1-indexed start line.
            - ``end_line`` (int, optional): 1-indexed inclusive end line.

    Returns:
        The file text content (full or sliced).

    Raises:
        FileNotFoundError: If the resolved path does not exist.
        PathContainmentError: If the path resolves outside the repo root.
    """
    resolved = resolve_and_validate(params["path"], _repo_root)

    if not os.path.isfile(resolved):
        raise FileNotFoundError(f"File not found: {params['path']}")

    with open(resolved, "r", encoding="utf-8") as f:
        content = f.read()

    start_line = params.get("start_line")
    end_line = params.get("end_line")

    if start_line is not None or end_line is not None:
        lines = content.splitlines(keepends=True)
        # Convert 1-indexed inclusive range to 0-indexed slice
        start = (start_line - 1) if start_line is not None else 0
        end = end_line if end_line is not None else len(lines)
        content = "".join(lines[start:end])

    return content


# --------------- JSON Schema for read_file ---------------

READ_FILE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "Relative file path within the repository",
        },
        "start_line": {
            "type": "integer",
            "description": "Starting line number (1-indexed, optional)",
        },
        "end_line": {
            "type": "integer",
            "description": "Ending line number (1-indexed, inclusive, optional)",
        },
    },
    "required": ["path"],
}


def make_read_file_tool() -> ToolDefinition:
    """Create a ToolDefinition for the read_file tool."""
    return ToolDefinition(
        name="read_file",
        description="Read the text content of a file, optionally limited to a line range.",
        parameters=READ_FILE_SCHEMA,
        handler=read_file,
    )


# --------------- list_directory ---------------


async def list_directory(params: dict) -> list[dict]:
    """List directory entries with name and type metadata.

    Args:
        params: Dict with keys:
            - ``path`` (str): Relative directory path within the repository.
            - ``depth`` (int, optional): Recursion depth (default 1).

    Returns:
        List of dicts with ``name`` (str) and ``type`` ("file" or "directory").

    Raises:
        FileNotFoundError: If the resolved path does not exist or is not a directory.
        PathContainmentError: If the path resolves outside the repo root.
    """
    resolved = resolve_and_validate(params["path"], _repo_root)

    if not os.path.isdir(resolved):
        raise FileNotFoundError(f"Directory not found: {params['path']}")

    depth = params.get("depth", 1)

    return _collect_entries(resolved, depth, prefix="")


def _collect_entries(base: str, depth: int, prefix: str) -> list[dict]:
    """Recursively collect directory entries up to *depth* levels.

    Args:
        base: Absolute path of the directory to scan.
        depth: Remaining levels to recurse (1 = immediate children only).
        prefix: Relative path prefix for nested entries.

    Returns:
        Flat list of ``{name, type}`` dicts.
    """
    if depth < 1:
        return []

    entries: list[dict] = []
    try:
        children = sorted(os.listdir(base))
    except PermissionError:
        return entries

    for child in children:
        full_path = os.path.join(base, child)
        relative = os.path.join(prefix, child) if prefix else child

        if os.path.isdir(full_path):
            entries.append({"name": relative, "type": "directory"})
            if depth > 1:
                entries.extend(_collect_entries(full_path, depth - 1, relative))
        else:
            entries.append({"name": relative, "type": "file"})

    return entries


# --------------- JSON Schema for list_directory ---------------

LIST_DIRECTORY_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "Relative directory path within the repository",
        },
        "depth": {
            "type": "integer",
            "description": "Recursion depth (default 1). 1 = immediate children only.",
        },
    },
    "required": ["path"],
}


def make_list_directory_tool() -> ToolDefinition:
    """Create a ToolDefinition for the list_directory tool."""
    return ToolDefinition(
        name="list_directory",
        description="List files and subdirectories in a directory with optional recursive depth.",
        parameters=LIST_DIRECTORY_SCHEMA,
        handler=list_directory,
    )


# =============== search_files ===============


async def search_files(params: dict) -> list[str]:
    """Search for files matching a glob pattern.

    Args:
        params: Dict with keys:
            - ``pattern`` (str): Glob pattern to match (e.g. ``"*.py"``, ``"**/*.txt"``).
            - ``base_dir`` (str, optional): Subdirectory to restrict the search to.
              Defaults to the repository root.

    Returns:
        List of matching file paths relative to the repository root.

    Raises:
        PathContainmentError: If base_dir resolves outside the repo root.
    """
    base_dir = params.get("base_dir", ".")
    pattern = params["pattern"]

    resolved_base = resolve_and_validate(base_dir, _repo_root)
    resolved_root = os.path.realpath(_repo_root)

    base_path = Path(resolved_base)
    matches: list[str] = []

    for match in base_path.glob(pattern):
        if match.is_file():
            rel = str(match.relative_to(resolved_root))
            matches.append(rel)

    return sorted(matches)


# --------------- JSON Schema for search_files ---------------

SEARCH_FILES_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "pattern": {
            "type": "string",
            "description": "Glob pattern to match files (e.g. '*.py', '**/*.txt')",
        },
        "base_dir": {
            "type": "string",
            "description": "Subdirectory to restrict the search to (optional, defaults to repo root)",
        },
    },
    "required": ["pattern"],
}


def make_search_files_tool() -> ToolDefinition:
    """Create a ToolDefinition for the search_files tool."""
    return ToolDefinition(
        name="search_files",
        description="Search for files matching a glob pattern within the repository.",
        parameters=SEARCH_FILES_SCHEMA,
        handler=search_files,
    )
