"""Search tools: grep_search.

Provides full-text search across repository files with optional
glob filtering and case-sensitivity control.  All file operations
go through ``resolve_and_validate()`` to ensure paths stay within
the configured repository root.
"""

import fnmatch
import os
import re

from server.path_utils import resolve_and_validate
from server.tool_registry import ToolDefinition

# Module-level repo root, set via ``set_repo_root()`` before tool use.
_repo_root: str = ""


def set_repo_root(repo_root: str) -> None:
    """Configure the repository root used by all search tools."""
    global _repo_root
    _repo_root = repo_root


async def grep_search(params: dict) -> list[dict]:
    """Search files line-by-line for a text query.

    Args:
        params: Dict with keys:
            - ``query`` (str): Text to search for.
            - ``include_pattern`` (str, optional): Glob pattern to filter files.
            - ``case_sensitive`` (bool, optional): Whether the search is
              case-sensitive.  Defaults to ``True``.

    Returns:
        List of match dicts, each containing ``file``, ``line_number``,
        ``content``, ``context_before``, and ``context_after``.
    """
    query: str = params["query"]
    include_pattern: str | None = params.get("include_pattern")
    case_sensitive: bool = params.get("case_sensitive", True)

    resolved_root = os.path.realpath(_repo_root)
    matches: list[dict] = []

    if case_sensitive:
        flags = 0
    else:
        flags = re.IGNORECASE

    pattern = re.compile(re.escape(query), flags)

    for dirpath, _dirnames, filenames in os.walk(resolved_root):
        for filename in filenames:
            abs_path = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(abs_path, resolved_root)

            # Filter by include_pattern if provided
            if include_pattern is not None:
                if not fnmatch.fnmatch(rel_path, include_pattern):
                    continue

            # Try to read the file; skip binary / unreadable files
            try:
                with open(abs_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
            except (UnicodeDecodeError, PermissionError, OSError):
                continue

            for idx, line in enumerate(lines):
                if pattern.search(line):
                    line_number = idx + 1  # 1-indexed

                    # 2 lines of context before
                    start = max(0, idx - 2)
                    context_before = [l.rstrip("\n\r") for l in lines[start:idx]]

                    # 2 lines of context after
                    end = min(len(lines), idx + 3)
                    context_after = [l.rstrip("\n\r") for l in lines[idx + 1 : end]]

                    matches.append(
                        {
                            "file": rel_path,
                            "line_number": line_number,
                            "content": line.rstrip("\n\r"),
                            "context_before": context_before,
                            "context_after": context_after,
                        }
                    )

    return matches


# --------------- JSON Schema for grep_search ---------------

GREP_SEARCH_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "Text query to search for in files",
        },
        "include_pattern": {
            "type": "string",
            "description": "Glob pattern to filter which files are searched (optional)",
        },
        "case_sensitive": {
            "type": "boolean",
            "description": "Whether the search is case-sensitive (default true)",
        },
    },
    "required": ["query"],
}


def make_grep_search_tool() -> ToolDefinition:
    """Create a ToolDefinition for the grep_search tool."""
    return ToolDefinition(
        name="grep_search",
        description=(
            "Search for a text pattern across repository files, returning "
            "matching lines with surrounding context."
        ),
        parameters=GREP_SEARCH_SCHEMA,
        handler=grep_search,
    )
