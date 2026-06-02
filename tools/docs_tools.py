"""Documentation search tools: docs_search.

Provides grep-style search over documentation-like files. The search
root is constrained to the configured repository root.
"""

import os
import re
from pathlib import Path

from server.path_utils import resolve_and_validate
from server.tool_registry import ToolDefinition

_repo_root: str = ""

DOC_EXTENSIONS = {".md", ".mdx", ".txt", ".rst"}
DEFAULT_MAX_RESULTS = 50


def set_repo_root(repo_root: str) -> None:
    """Configure the repository root used by documentation tools."""
    global _repo_root
    _repo_root = repo_root


def _default_docs_root() -> str:
    """Return the default documentation search root."""
    resolved_root = os.path.realpath(_repo_root)
    docs_dir = os.path.join(resolved_root, "docs")
    data_docs_dir = os.path.join(resolved_root, "data", "docs")

    if os.path.isdir(docs_dir):
        return docs_dir
    if os.path.isdir(data_docs_dir):
        return data_docs_dir
    return resolved_root


def _is_doc_file(path: str) -> bool:
    """Return true when *path* has a documentation-like extension."""
    return Path(path).suffix.lower() in DOC_EXTENSIONS


async def docs_search(params: dict) -> list[dict]:
    """Search documentation-like files for a literal query."""
    query: str = params["query"]
    docs_dir = params.get("docs_dir")
    case_sensitive: bool = params.get("case_sensitive", False)
    max_results: int = params.get("max_results", DEFAULT_MAX_RESULTS)

    if docs_dir is not None:
        search_root = resolve_and_validate(docs_dir, _repo_root)
    else:
        search_root = _default_docs_root()

    if not os.path.isdir(search_root):
        raise FileNotFoundError(f"Documentation directory not found: {docs_dir}")

    resolved_repo_root = os.path.realpath(_repo_root)
    flags = 0 if case_sensitive else re.IGNORECASE
    pattern = re.compile(re.escape(query), flags)
    matches: list[dict] = []

    for dirpath, _dirnames, filenames in os.walk(search_root):
        for filename in sorted(filenames):
            abs_path = os.path.join(dirpath, filename)
            if not _is_doc_file(abs_path):
                continue

            rel_path = os.path.relpath(abs_path, resolved_repo_root)

            try:
                with open(abs_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
            except (UnicodeDecodeError, PermissionError, OSError):
                continue

            for idx, line in enumerate(lines):
                if not pattern.search(line):
                    continue

                start = max(0, idx - 2)
                end = min(len(lines), idx + 3)
                matches.append(
                    {
                        "file": rel_path,
                        "line_number": idx + 1,
                        "content": line.rstrip("\n\r"),
                        "context_before": [
                            l.rstrip("\n\r") for l in lines[start:idx]
                        ],
                        "context_after": [
                            l.rstrip("\n\r") for l in lines[idx + 1 : end]
                        ],
                    }
                )
                if len(matches) >= max_results:
                    return matches

    return matches


DOCS_SEARCH_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "Literal text query to search for in documentation files",
        },
        "docs_dir": {
            "type": "string",
            "description": "Documentation directory to search, relative to the repository root",
        },
        "case_sensitive": {
            "type": "boolean",
            "description": "Whether the search is case-sensitive (default false)",
        },
        "max_results": {
            "type": "integer",
            "minimum": 1,
            "description": "Maximum number of matches to return (default 50)",
        },
    },
    "required": ["query"],
}


def make_docs_search_tool() -> ToolDefinition:
    """Create a ToolDefinition for the docs_search tool."""
    return ToolDefinition(
        name="docs_search",
        description=(
            "Search documentation-like files (.md, .mdx, .txt, .rst) "
            "for literal text matches with surrounding context."
        ),
        parameters=DOCS_SEARCH_SCHEMA,
        handler=docs_search,
    )
