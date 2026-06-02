"""General search tool plugin."""

from server.tool_registry import ToolRegistry
from tools.search_tools import make_grep_search_tool
from tools.search_tools import set_repo_root as set_search_repo_root


def register(registry: ToolRegistry, repo_root: str) -> None:
    """Register general search tools."""
    set_search_repo_root(repo_root)
    registry.register(make_grep_search_tool())
