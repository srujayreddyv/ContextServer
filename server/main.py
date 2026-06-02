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
from tool_plugins import register_all

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
        choices=["stdio"],
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

    # Build the tool registry through internal tool plugins.
    registry = ToolRegistry()
    register_all(registry, resolved_root)

    print(f"Starting ContextServer with transport: {effective_transport}", file=sys.stderr)

    server = ContextMCPServer(
        registry=registry,
        repo_root=resolved_root,
        transport=effective_transport,
    )

    asyncio.run(server.run())


if __name__ == "__main__":
    main()
