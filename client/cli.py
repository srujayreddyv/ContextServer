"""Interactive CLI client for the ContextServer.

Spawns the ContextServer as a subprocess over stdio transport and
provides a simple REPL for listing and invoking tools.

Usage::

    python -m client.cli --repo-root /path/to/repo

Commands:
    list_tools              List all available tools
    call <name> <json>      Invoke a tool with JSON parameters
    help                    Show available commands
    quit / exit             Exit the client
"""

import argparse
import asyncio
import json
import os
import sys

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


async def run_client(repo_root: str) -> None:
    """Connect to the ContextServer and run an interactive REPL."""
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "server.main", "--repo-root", repo_root],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )

    print(f"Connecting to ContextServer (repo: {repo_root}) ...")

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            print("Connected. Type 'help' for available commands.\n")

            while True:
                try:
                    line = await asyncio.to_thread(input, "mcp> ")
                except (EOFError, KeyboardInterrupt):
                    print()
                    break

                line = line.strip()
                if not line:
                    continue

                parts = line.split(None, 1)
                command = parts[0].lower()

                if command in ("quit", "exit"):
                    break
                elif command == "help":
                    _print_help()
                elif command == "list_tools":
                    await _handle_list_tools(session)
                elif command == "call":
                    if len(parts) < 2:
                        print("Usage: call <tool_name> <json_params>")
                        continue
                    await _handle_call(session, parts[1])
                else:
                    print(f"Unknown command: {command}. Type 'help' for usage.")

    print("Disconnected.")


def _print_help() -> None:
    """Print available REPL commands."""
    print(
        "Commands:\n"
        "  list_tools              List all available tools\n"
        "  call <name> <json>      Invoke a tool (e.g. call read_file {\"path\": \"README.md\"})\n"
        "  help                    Show this help message\n"
        "  quit / exit             Exit the client"
    )


async def _handle_list_tools(session: ClientSession) -> None:
    """List all tools exposed by the server."""
    result = await session.list_tools()
    if not result.tools:
        print("No tools available.")
        return
    for tool in result.tools:
        desc = f" — {tool.description}" if tool.description else ""
        print(f"  {tool.name}{desc}")


async def _handle_call(session: ClientSession, args_str: str) -> None:
    """Parse tool name + JSON params and invoke the tool."""
    parts = args_str.split(None, 1)
    tool_name = parts[0]
    params: dict = {}

    if len(parts) > 1:
        try:
            params = json.loads(parts[1])
        except json.JSONDecodeError as exc:
            print(f"Invalid JSON parameters: {exc}")
            return

    try:
        result = await session.call_tool(tool_name, params)
        if result.isError:
            print(f"[ERROR] ", end="")
        for content in result.content:
            print(content.text if hasattr(content, "text") else str(content))
    except Exception as exc:
        print(f"Error calling tool: {exc}")


def main() -> None:
    """Entry point for the CLI client."""
    parser = argparse.ArgumentParser(
        description="Interactive MCP client for ContextServer",
    )
    parser.add_argument(
        "--repo-root",
        default=os.getcwd(),
        help="Path to the repository root (defaults to current directory)",
    )
    args = parser.parse_args()

    repo_root = os.path.realpath(args.repo_root)
    if not os.path.isdir(repo_root):
        print(f"Error: not a directory: {repo_root}", file=sys.stderr)
        sys.exit(1)

    asyncio.run(run_client(repo_root))


if __name__ == "__main__":
    main()
