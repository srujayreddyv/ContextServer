"""Documentation search tool plugin."""

from server.tool_registry import ToolRegistry
from tools.docs_tools import make_docs_search_tool
from tools.docs_tools import set_repo_root as set_docs_repo_root


def register(registry: ToolRegistry, repo_root: str) -> None:
    """Register documentation tools."""
    set_docs_repo_root(repo_root)
    registry.register(make_docs_search_tool())
