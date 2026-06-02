"""Filesystem tool plugin."""

from server.tool_registry import ToolRegistry
from tools.filesystem_tools import (
    make_list_directory_tool,
    make_read_file_tool,
    make_search_files_tool,
)
from tools.filesystem_tools import set_repo_root as set_filesystem_repo_root


def register(registry: ToolRegistry, repo_root: str) -> None:
    """Register filesystem tools."""
    set_filesystem_repo_root(repo_root)
    registry.register(make_read_file_tool())
    registry.register(make_list_directory_tool())
    registry.register(make_search_files_tool())
