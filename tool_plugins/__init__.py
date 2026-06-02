"""Internal tool plugin registration helpers."""

from server.tool_registry import ToolRegistry

from tool_plugins import docs, filesystem, git, search


def register_all(registry: ToolRegistry, repo_root: str) -> None:
    """Register all built-in internal tool plugins."""
    filesystem.register(registry, repo_root)
    git.register(registry, repo_root)
    search.register(registry, repo_root)
    docs.register(registry, repo_root)
