"""Git tool plugin."""

from server.tool_registry import ToolRegistry
from tools.git_tools import (
    make_git_branches_tool,
    make_git_diff_tool,
    make_git_log_tool,
    make_git_status_tool,
)
from tools.git_tools import set_repo_root as set_git_repo_root


def register(registry: ToolRegistry, repo_root: str) -> None:
    """Register Git tools."""
    set_git_repo_root(repo_root)
    registry.register(make_git_log_tool())
    registry.register(make_git_diff_tool())
    registry.register(make_git_status_tool())
    registry.register(make_git_branches_tool())
