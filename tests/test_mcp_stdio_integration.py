"""End-to-end MCP stdio integration tests."""

import os
import sys

import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


@pytest.mark.asyncio
async def test_mcp_stdio_lists_and_calls_tools(tmp_path):
    """Start the server over stdio and exercise tools/list + tools/call."""
    (tmp_path / "README.md").write_text(
        "# Sample Repo\n\nContextServer can inspect this repository.\n",
        encoding="utf-8",
    )
    docs_dir = tmp_path / "data" / "docs"
    docs_dir.mkdir(parents=True)
    (docs_dir / "guide.md").write_text(
        "# Guide\n\nContextServer documentation search works here.\n",
        encoding="utf-8",
    )

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "server.main", "--repo-root", str(tmp_path)],
        cwd=project_root,
    )

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            tools_result = await session.list_tools()
            tool_names = {tool.name for tool in tools_result.tools}
            assert "read_file" in tool_names
            assert "docs_search" in tool_names

            read_result = await session.call_tool(
                "read_file",
                {"path": "README.md", "start_line": 1, "end_line": 1},
            )
            assert not read_result.isError
            assert read_result.content[0].text == "# Sample Repo\n"

            docs_result = await session.call_tool(
                "docs_search",
                {"query": "contextserver"},
            )
            assert not docs_result.isError
            assert "data/docs/guide.md" in docs_result.content[0].text
