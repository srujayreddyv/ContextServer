"""Entry point for the ContextServer.

Parses CLI arguments, validates the repository root, registers all
tools, and starts the MCP server on the chosen transport.
"""

import argparse
import asyncio
import logging
import os
import sys

from server.mcp_server import ContextMCPServer
from server.tool_registry import ToolRegistry
from tools.filesystem_tools import (
    make_list_directory_tool,
    make_read_file_tool,
    make_search_files_tool,
)
from tools.filesystem_tools import set_repo_root as fs_set_repo_root
from tools.git_tools import (
    make_git_branches_tool,
    make_git_diff_tool,
    make_git_log_tool,
    make_git_status_tool,
)
from tools.git_tools import set_repo_root as git_set_repo_root
from tools.search_tools import make_grep_search_tool
from tools.search_tools import set_repo_root as search_set_repo_root

logger = logging.getLogger(__name__)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="ContextServer — MCP tool server for repository inspection",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Path to the repository root (defaults to current working directory)",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="MCP transport type (default: stdio)",
    )
    return parser.parse_args(argv)


def _validate_repo_root(path: str) -> str:
    """Resolve and validate the repository root path.

    Returns the resolved absolute path.

    Raises:
        SystemExit: If the path does not exist or is not a directory.
    """
    resolved = os.path.realpath(path)
    if not os.path.exists(resolved):
        print(f"Error: repository root does not exist: {resolved}", file=sys.stderr)
        sys.exit(1)
    if not os.path.isdir(resolved):
        print(f"Error: repository root is not a directory: {resolved}", file=sys.stderr)
        sys.exit(1)
    return resolved


def main(repo_root: str | None = None, transport: str = "stdio") -> None:
    """Start the ContextServer with the given configuration."""
    args = _parse_args()

    # CLI args override function parameters
    effective_root = args.repo_root or repo_root or os.getcwd()
    effective_transport = args.transport or transport

    resolved_root = _validate_repo_root(effective_root)

    # Configure tool modules with the repo root
    fs_set_repo_root(resolved_root)
    git_set_repo_root(resolved_root)
    search_set_repo_root(resolved_root)

    # Build the tool registry
    registry = ToolRegistry()
    registry.register(make_read_file_tool())
    registry.register(make_list_directory_tool())
    registry.register(make_search_files_tool())
    registry.register(make_git_log_tool())
    registry.register(make_git_diff_tool())
    registry.register(make_git_status_tool())
    registry.register(make_git_branches_tool())
    registry.register(make_grep_search_tool())

    print(f"Starting ContextServer with transport: {effective_transport}", file=sys.stderr)

    server = ContextMCPServer(
        registry=registry,
        repo_root=resolved_root,
        transport=effective_transport,
    )

    asyncio.run(server.run())


if __name__ == "__main__":
    main()
