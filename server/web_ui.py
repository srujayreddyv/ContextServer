"""Local web UI for managing and calling stdio MCP servers."""

import argparse
import asyncio
import json
import os
import re
import shlex
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONFIG_PATH = os.path.join(PROJECT_ROOT, ".contextserver", "mcp_servers.json")


def _default_config_path() -> str:
    """Return the config path for user-added MCP servers."""
    return os.environ.get("CONTEXTSERVER_UI_CONFIG", DEFAULT_CONFIG_PATH)


def _slugify(value: str) -> str:
    """Create a stable-ish readable id prefix."""
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "server"


def _normalize_args(args: Any) -> list[str]:
    """Normalize JSON args from either a string or list of strings."""
    if args is None:
        return []
    if isinstance(args, str):
        return shlex.split(args)
    if isinstance(args, list) and all(isinstance(arg, str) for arg in args):
        return args
    raise ValueError("args must be a shell-style string or a list of strings")


def _normalize_server(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a user-provided MCP server config."""
    name = str(payload.get("name", "")).strip()
    command = str(payload.get("command", "")).strip()
    cwd = str(payload.get("cwd", "")).strip() or None
    args = _normalize_args(payload.get("args"))
    env = payload.get("env")

    if not name:
        raise ValueError("name is required")
    if not command:
        raise ValueError("command is required")
    if env is not None and not (
        isinstance(env, dict)
        and all(isinstance(k, str) and isinstance(v, str) for k, v in env.items())
    ):
        raise ValueError("env must be an object with string keys and values")

    return {
        "id": f"{_slugify(name)}-{uuid4().hex[:8]}",
        "name": name,
        "command": command,
        "args": args,
        "cwd": cwd,
        "env": env,
        "builtin": False,
    }


def _builtin_context_server(repo_root: str) -> dict[str, Any]:
    """Return the built-in ContextServer stdio config."""
    return {
        "id": "contextserver",
        "name": "ContextServer",
        "command": sys.executable,
        "args": ["-m", "server.main", "--repo-root", repo_root],
        "cwd": PROJECT_ROOT,
        "env": None,
        "builtin": True,
    }


def _read_user_servers(config_path: str) -> list[dict[str, Any]]:
    """Read persisted user-added MCP servers."""
    if not os.path.exists(config_path):
        return []
    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("MCP server config must contain a JSON list")
    return data


def _write_user_servers(config_path: str, servers: list[dict[str, Any]]) -> None:
    """Persist user-added MCP servers."""
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(servers, f, indent=2)
        f.write("\n")


def _load_servers(config_path: str, repo_root: str) -> list[dict[str, Any]]:
    """Return built-in and user-added MCP server configs."""
    return [_builtin_context_server(repo_root), *_read_user_servers(config_path)]


def _public_server(server: dict[str, Any]) -> dict[str, Any]:
    """Return server fields safe to send to the UI."""
    return {
        "id": server["id"],
        "name": server["name"],
        "command": server["command"],
        "args": server.get("args", []),
        "cwd": server.get("cwd"),
        "builtin": server.get("builtin", False),
    }


def _find_server(
    server_id: str,
    config_path: str,
    repo_root: str,
) -> dict[str, Any] | None:
    """Find a configured MCP server by id."""
    for server in _load_servers(config_path, repo_root):
        if server["id"] == server_id:
            return server
    return None


def _add_user_server(
    config_path: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Add and persist a user MCP server config."""
    server = _normalize_server(payload)
    servers = _read_user_servers(config_path)
    servers.append(server)
    _write_user_servers(config_path, servers)
    return server


def _delete_user_server(config_path: str, server_id: str) -> bool:
    """Delete a persisted user MCP server config by id."""
    servers = _read_user_servers(config_path)
    remaining = [server for server in servers if server["id"] != server_id]
    if len(remaining) == len(servers):
        return False
    _write_user_servers(config_path, remaining)
    return True


async def _list_tools(server: dict[str, Any]) -> list[dict[str, Any]]:
    """List tools from an MCP stdio server."""
    params = StdioServerParameters(
        command=server["command"],
        args=server.get("args", []),
        cwd=server.get("cwd"),
        env=server.get("env"),
    )
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.list_tools()
            return [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "inputSchema": tool.inputSchema,
                }
                for tool in result.tools
            ]


async def _call_tool(
    server: dict[str, Any],
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Call a tool on an MCP stdio server."""
    params = StdioServerParameters(
        command=server["command"],
        args=server.get("args", []),
        cwd=server.get("cwd"),
        env=server.get("env"),
    )
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            return {
                "isError": bool(result.isError),
                "content": [
                    content.text if hasattr(content, "text") else str(content)
                    for content in result.content
                ],
            }


class WebUIHandler(BaseHTTPRequestHandler):
    """HTTP handler for the local dashboard."""

    config_path = DEFAULT_CONFIG_PATH
    repo_root = os.getcwd()

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self._send_html(INDEX_HTML)
            return
        if path == "/api/servers":
            self._handle_list_servers()
            return
        match = re.fullmatch(r"/api/servers/([^/]+)/tools", path)
        if match:
            self._handle_list_tools(match.group(1))
            return
        self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/servers":
            self._handle_add_server()
            return
        match = re.fullmatch(r"/api/servers/([^/]+)/call", path)
        if match:
            self._handle_call_tool(match.group(1))
            return
        self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_DELETE(self) -> None:
        match = re.fullmatch(r"/api/servers/([^/]+)", urlparse(self.path).path)
        if match:
            self._handle_delete_server(match.group(1))
            return
        self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: Any) -> None:
        """Keep the dashboard quiet except for explicit startup output."""

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        if not raw:
            return {}
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("request body must be a JSON object")
        return data

    def _send_html(self, html: str) -> None:
        encoded = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_json(
        self,
        payload: dict[str, Any] | list[Any],
        status: HTTPStatus = HTTPStatus.OK,
    ) -> None:
        encoded = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _handle_list_servers(self) -> None:
        try:
            servers = _load_servers(self.config_path, self.repo_root)
            self._send_json([_public_server(server) for server in servers])
        except Exception as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def _handle_add_server(self) -> None:
        try:
            server = _add_user_server(self.config_path, self._read_json())
            self._send_json(_public_server(server), HTTPStatus.CREATED)
        except (ValueError, json.JSONDecodeError) as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def _handle_delete_server(self, server_id: str) -> None:
        try:
            if server_id == "contextserver":
                self._send_json(
                    {"error": "built-in server cannot be deleted"},
                    HTTPStatus.BAD_REQUEST,
                )
                return
            if not _delete_user_server(self.config_path, server_id):
                self._send_json({"error": "server not found"}, HTTPStatus.NOT_FOUND)
                return
            self._send_json({"ok": True})
        except Exception as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def _handle_list_tools(self, server_id: str) -> None:
        server = _find_server(server_id, self.config_path, self.repo_root)
        if server is None:
            self._send_json({"error": "server not found"}, HTTPStatus.NOT_FOUND)
            return
        try:
            self._send_json(asyncio.run(_list_tools(server)))
        except Exception as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_GATEWAY)

    def _handle_call_tool(self, server_id: str) -> None:
        server = _find_server(server_id, self.config_path, self.repo_root)
        if server is None:
            self._send_json({"error": "server not found"}, HTTPStatus.NOT_FOUND)
            return
        try:
            payload = self._read_json()
            tool_name = str(payload.get("tool", "")).strip()
            arguments = payload.get("arguments", {})
            if not tool_name:
                raise ValueError("tool is required")
            if not isinstance(arguments, dict):
                raise ValueError("arguments must be a JSON object")
            self._send_json(asyncio.run(_call_tool(server, tool_name, arguments)))
        except (ValueError, json.JSONDecodeError) as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_GATEWAY)


INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ContextServer MCP Workbench</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f8fb;
      --panel: #ffffff;
      --text: #152033;
      --muted: #607089;
      --line: #d8e0ea;
      --accent: #1b6f7a;
      --accent-2: #2f7d4f;
      --danger: #b42318;
      --code: #0f172a;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 20px;
      padding: 20px 28px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }
    h1, h2, h3 { margin: 0; letter-spacing: 0; }
    h1 { font-size: 22px; }
    h2 { font-size: 16px; margin-bottom: 12px; }
    h3 { font-size: 14px; }
    .subtitle { color: var(--muted); margin-top: 4px; font-size: 14px; }
    main {
      display: grid;
      grid-template-columns: 320px minmax(0, 1fr);
      gap: 18px;
      padding: 18px;
      min-height: calc(100vh - 82px);
    }
    aside, section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
    }
    .server-list {
      display: grid;
      gap: 8px;
      margin-bottom: 18px;
    }
    .server-button {
      width: 100%;
      text-align: left;
      border: 1px solid var(--line);
      background: #fff;
      border-radius: 8px;
      padding: 10px;
      cursor: pointer;
    }
    .server-button.active {
      border-color: var(--accent);
      outline: 2px solid rgba(27, 111, 122, .14);
    }
    .server-meta {
      color: var(--muted);
      font-size: 12px;
      overflow-wrap: anywhere;
      margin-top: 3px;
    }
    label {
      display: block;
      color: var(--muted);
      font-size: 12px;
      font-weight: 600;
      margin: 10px 0 5px;
    }
    input, textarea, select {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 9px;
      font: inherit;
      background: #fff;
      color: var(--text);
    }
    textarea {
      min-height: 92px;
      resize: vertical;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 13px;
    }
    button {
      border: 1px solid transparent;
      border-radius: 6px;
      padding: 9px 12px;
      font-weight: 650;
      cursor: pointer;
      background: var(--accent);
      color: #fff;
    }
    button.secondary {
      color: var(--accent);
      background: #fff;
      border-color: var(--accent);
    }
    button.danger {
      color: var(--danger);
      background: #fff;
      border-color: #f1b5ae;
    }
    .row {
      display: flex;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
    }
    .grid {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      gap: 14px;
    }
    .tools {
      display: grid;
      gap: 8px;
      margin-top: 10px;
    }
    .tool {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      background: #fff;
    }
    .tool-name {
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      color: var(--accent);
      font-weight: 700;
    }
    .tool-desc {
      margin-top: 4px;
      color: var(--muted);
      font-size: 13px;
    }
    pre {
      margin: 0;
      padding: 12px;
      min-height: 180px;
      max-height: 420px;
      overflow: auto;
      border-radius: 8px;
      background: var(--code);
      color: #e5edf7;
      font-size: 13px;
      line-height: 1.45;
      white-space: pre-wrap;
    }
    .status {
      min-height: 20px;
      color: var(--muted);
      font-size: 13px;
    }
    .warning {
      border-left: 3px solid var(--accent-2);
      padding: 8px 10px;
      color: var(--muted);
      background: #f4fbf7;
      font-size: 13px;
      margin-bottom: 12px;
    }
    @media (max-width: 880px) {
      main { grid-template-columns: 1fr; }
      .grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>ContextServer MCP Workbench</h1>
      <div class="subtitle">Manage local stdio MCP servers, inspect tools, and call them from one dashboard.</div>
    </div>
    <button class="secondary" id="refreshServers">Refresh</button>
  </header>
  <main>
    <aside>
      <h2>MCP Servers</h2>
      <div class="server-list" id="servers"></div>

      <h2>Add Server</h2>
      <div class="warning">Commands run locally. Add only MCP servers you trust.</div>
      <form id="addServerForm">
        <label for="name">Name</label>
        <input id="name" name="name" placeholder="Filesystem MCP">
        <label for="command">Command</label>
        <input id="command" name="command" placeholder="python">
        <label for="args">Args</label>
        <input id="args" name="args" placeholder="-m some_mcp_server --flag value">
        <label for="cwd">Working directory</label>
        <input id="cwd" name="cwd" placeholder="/path/to/server">
        <div class="row" style="margin-top: 12px;">
          <button type="submit">Add server</button>
          <button type="button" class="danger" id="deleteServer">Delete selected</button>
        </div>
      </form>
    </aside>

    <section>
      <div class="row" style="justify-content: space-between; margin-bottom: 12px;">
        <div>
          <h2 id="selectedTitle">No server selected</h2>
          <div class="status" id="status"></div>
        </div>
        <button id="loadTools">List tools</button>
      </div>

      <div class="grid">
        <div>
          <h2>Tools</h2>
          <div class="tools" id="tools"></div>
        </div>
        <div>
          <h2>Call Tool</h2>
          <label for="toolName">Tool</label>
          <select id="toolName"></select>
          <label for="arguments">Arguments JSON</label>
          <textarea id="arguments">{
  "query": "ContextServer"
}</textarea>
          <div class="row" style="margin-top: 10px;">
            <button id="callTool">Call tool</button>
            <button class="secondary" id="formatJson">Format JSON</button>
          </div>
          <h2 style="margin-top: 16px;">Result</h2>
          <pre id="result">Select a server, list tools, then call one.</pre>
        </div>
      </div>
    </section>
  </main>

  <script>
    let servers = [];
    let selectedServerId = null;
    let currentTools = [];

    const $ = (id) => document.getElementById(id);

    function setStatus(message) {
      $("status").textContent = message || "";
    }

    function renderServers() {
      const container = $("servers");
      container.innerHTML = "";
      servers.forEach((server) => {
        const button = document.createElement("button");
        button.className = "server-button" + (server.id === selectedServerId ? " active" : "");
        button.type = "button";
        button.innerHTML = `
          <h3>${escapeHtml(server.name)}${server.builtin ? " · built-in" : ""}</h3>
          <div class="server-meta">${escapeHtml(server.command)} ${escapeHtml((server.args || []).join(" "))}</div>
        `;
        button.addEventListener("click", () => selectServer(server.id));
        container.appendChild(button);
      });
    }

    function selectServer(id) {
      selectedServerId = id;
      currentTools = [];
      const server = servers.find((item) => item.id === id);
      $("selectedTitle").textContent = server ? server.name : "No server selected";
      $("tools").innerHTML = "";
      $("toolName").innerHTML = "";
      $("result").textContent = "Click List tools to inspect this MCP server.";
      renderServers();
    }

    async function loadServers() {
      setStatus("Loading servers...");
      const response = await fetch("/api/servers");
      servers = await response.json();
      if (!response.ok) throw new Error(servers.error || "Failed to load servers");
      if (!selectedServerId && servers.length) selectedServerId = servers[0].id;
      renderServers();
      selectServer(selectedServerId);
      setStatus("");
    }

    async function loadTools() {
      if (!selectedServerId) return;
      setStatus("Starting MCP server and listing tools...");
      $("tools").innerHTML = "";
      $("toolName").innerHTML = "";
      const response = await fetch(`/api/servers/${selectedServerId}/tools`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Failed to list tools");
      currentTools = data;
      const toolsContainer = $("tools");
      data.forEach((tool) => {
        const item = document.createElement("div");
        item.className = "tool";
        item.innerHTML = `
          <div class="tool-name">${escapeHtml(tool.name)}</div>
          <div class="tool-desc">${escapeHtml(tool.description || "")}</div>
        `;
        item.addEventListener("click", () => {
          selectTool(tool.name);
        });
        toolsContainer.appendChild(item);

        const option = document.createElement("option");
        option.value = tool.name;
        option.textContent = tool.name;
        $("toolName").appendChild(option);
      });
      if (data.length) selectTool(data[0].name);
      setStatus(`${data.length} tools available`);
    }

    function selectTool(toolName) {
      $("toolName").value = toolName;
      const tool = currentTools.find((item) => item.name === toolName);
      if (!tool) return;
      $("arguments").value = JSON.stringify(exampleArguments(tool), null, 2);
      $("result").textContent = JSON.stringify(tool.inputSchema, null, 2);
    }

    function exampleArguments(tool) {
      const examples = {
        read_file: {path: "README.md", start_line: 1, end_line: 5},
        list_directory: {path: ".", depth: 1},
        search_files: {pattern: "**/*.py"},
        git_log: {max_count: 5},
        git_diff: {},
        git_status: {},
        git_branches: {},
        grep_search: {query: "ContextServer", include_pattern: "*.md"},
        docs_search: {query: "ContextServer"}
      };
      if (examples[tool.name]) return examples[tool.name];

      const schema = tool.inputSchema || {};
      const properties = schema.properties || {};
      const required = schema.required || [];
      const args = {};
      required.forEach((name) => {
        const property = properties[name] || {};
        if (property.type === "integer" || property.type === "number") args[name] = property.minimum || 1;
        else if (property.type === "boolean") args[name] = false;
        else if (property.type === "array") args[name] = [];
        else if (property.type === "object") args[name] = {};
        else args[name] = "";
      });
      return args;
    }

    async function addServer(event) {
      event.preventDefault();
      const payload = {
        name: $("name").value,
        command: $("command").value,
        args: $("args").value,
        cwd: $("cwd").value
      };
      const response = await fetch("/api/servers", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload)
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Failed to add server");
      selectedServerId = data.id;
      event.target.reset();
      await loadServers();
    }

    async function deleteSelectedServer() {
      if (!selectedServerId || selectedServerId === "contextserver") return;
      const response = await fetch(`/api/servers/${selectedServerId}`, {method: "DELETE"});
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Failed to delete server");
      selectedServerId = null;
      await loadServers();
    }

    async function callTool() {
      if (!selectedServerId) return;
      const tool = $("toolName").value;
      const argsText = $("arguments").value.trim() || "{}";
      const payload = {tool, arguments: JSON.parse(argsText)};
      setStatus(`Calling ${tool}...`);
      const response = await fetch(`/api/servers/${selectedServerId}/call`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload)
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Tool call failed");
      $("result").textContent = JSON.stringify(data, null, 2);
      setStatus(data.isError ? "Tool returned an error" : "Tool call complete");
    }

    function formatArguments() {
      $("arguments").value = JSON.stringify(JSON.parse($("arguments").value || "{}"), null, 2);
    }

    function escapeHtml(value) {
      return String(value).replace(/[&<>"']/g, (char) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;"
      })[char]);
    }

    function showError(error) {
      setStatus(error.message);
      $("result").textContent = error.stack || error.message;
    }

    $("refreshServers").addEventListener("click", () => loadServers().catch(showError));
    $("loadTools").addEventListener("click", () => loadTools().catch(showError));
    $("addServerForm").addEventListener("submit", (event) => addServer(event).catch(showError));
    $("deleteServer").addEventListener("click", () => deleteSelectedServer().catch(showError));
    $("callTool").addEventListener("click", () => callTool().catch(showError));
    $("toolName").addEventListener("change", () => selectTool($("toolName").value));
    $("formatJson").addEventListener("click", () => {
      try { formatArguments(); } catch (error) { showError(error); }
    });

    loadServers().catch(showError);
  </script>
</body>
</html>
"""


def run_web_ui(
    host: str = "127.0.0.1",
    port: int = 8765,
    repo_root: str | None = None,
    config_path: str | None = None,
) -> None:
    """Run the local web UI server."""
    resolved_root = os.path.realpath(repo_root or os.getcwd())
    WebUIHandler.repo_root = resolved_root
    WebUIHandler.config_path = config_path or _default_config_path()

    httpd = ThreadingHTTPServer((host, port), WebUIHandler)
    print(f"ContextServer UI: http://{host}:{port}", file=sys.stderr)
    print(f"Repository root: {resolved_root}", file=sys.stderr)
    print(f"MCP server config: {WebUIHandler.config_path}", file=sys.stderr)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


def main() -> None:
    """CLI entry point for the local web UI."""
    parser = argparse.ArgumentParser(description="ContextServer local MCP workbench")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind")
    parser.add_argument("--port", type=int, default=8765, help="Port to bind")
    parser.add_argument(
        "--repo-root",
        default=os.getcwd(),
        help="Repository root for the built-in ContextServer entry",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to persisted MCP server config JSON",
    )
    args = parser.parse_args()

    run_web_ui(
        host=args.host,
        port=args.port,
        repo_root=args.repo_root,
        config_path=args.config,
    )


if __name__ == "__main__":
    main()
