# ContextServer

An MCP (Model Context Protocol) compatible tool server that exposes filesystem, Git, and documentation search capabilities to AI agents. ContextServer enables automated repository inspection and contextual retrieval through a standardized protocol interface.

```
AI Agent / CLI Client
        │
   MCP Transport (stdio)
        │
   ContextServer
        │
   ┌────┴─────────────────┐
   │    Tool Registry      │
   └────┬─────────────────┘
        │
   ┌────┼────────────┐
   │    │             │
Filesystem  Git    Search
 Tools     Tools    Tools
```

## Features

- **MCP Protocol Compliance** — Full MCP handshake, tool discovery (`tools/list`), and tool invocation (`tools/call`) via the official `mcp` Python SDK
- **8 Built-in Tools** across filesystem, Git, and search categories
- **Path Containment Security** — All file operations are sandboxed within the configured repository root; symlink escape and `../` traversal are blocked
- **Read-Only by Design** — No tools create, modify, or delete files
- **Interactive CLI Client** — REPL for testing tools manually over stdio transport

## Requirements

- Python 3.10+
- Git (for Git tools)

## Installation

```bash
pip install -e .
```

For development (includes test dependencies):

```bash
pip install -e ".[dev]"
```

> Requires Python 3.10+. If your system Python is older, create a venv with a compatible version first:
>
> ```bash
> python3.10 -m venv .venv && source .venv/bin/activate
> ```

### Dependencies

| Package          | Purpose                            |
| ---------------- | ---------------------------------- |
| `mcp`            | MCP protocol SDK (server + client) |
| `jsonschema`     | Tool parameter validation          |
| `pytest`         | Test framework (dev)               |
| `pytest-asyncio` | Async test support (dev)           |
| `hypothesis`     | Property-based testing (dev)       |

## Quick Start

### Start the Server

```bash
# Serve the current directory
python -m server.main

# Serve a specific repository
python -m server.main --repo-root /path/to/your/repo

# Specify transport (default: stdio)
python -m server.main --repo-root /path/to/repo --transport stdio
```

### Use the Interactive CLI Client

```bash
# Connect to a repo
python -m client.cli --repo-root /path/to/your/repo
```

Once connected, you get a REPL:

```
Connecting to ContextServer (repo: /path/to/your/repo) ...
Connected. Type 'help' for available commands.

mcp> list_tools
mcp> call read_file {"path": "README.md"}
mcp> call list_directory {"path": ".", "depth": 2}
mcp> call git_log {"max_count": 5}
mcp> call grep_search {"query": "TODO", "include_pattern": "*.py"}
mcp> quit
```

### CLI Client Commands

| Command              | Description                        |
| -------------------- | ---------------------------------- |
| `list_tools`         | List all available tools           |
| `call <name> <json>` | Invoke a tool with JSON parameters |
| `help`               | Show available commands            |
| `quit` / `exit`      | Exit the client                    |

## Tool Reference

### Filesystem Tools

#### `read_file`

Read the text content of a file, optionally limited to a line range.

| Parameter    | Type    | Required | Description                               |
| ------------ | ------- | -------- | ----------------------------------------- |
| `path`       | string  | Yes      | Relative file path within the repository  |
| `start_line` | integer | No       | Starting line number (1-indexed)          |
| `end_line`   | integer | No       | Ending line number (1-indexed, inclusive) |

**Returns:** File text content as a string.

**Examples:**

```json
{"path": "src/main.py"}
{"path": "src/main.py", "start_line": 10, "end_line": 25}
```

**Errors:**

- `FileNotFoundError` — Path does not exist
- `PathContainmentError` — Path resolves outside the repository root

---

#### `list_directory`

List files and subdirectories with optional recursive depth.

| Parameter | Type    | Required | Description                                              |
| --------- | ------- | -------- | -------------------------------------------------------- |
| `path`    | string  | Yes      | Relative directory path within the repository            |
| `depth`   | integer | No       | Recursion depth (default 1). 1 = immediate children only |

**Returns:** List of `{"name": "...", "type": "file"|"directory"}` entries.

**Examples:**

```json
{"path": "."}
{"path": "src", "depth": 3}
```

**Errors:**

- `FileNotFoundError` — Directory does not exist or path is a file
- `PathContainmentError` — Path resolves outside the repository root

---

#### `search_files`

Search for files matching a glob pattern.

| Parameter  | Type   | Required | Description                                            |
| ---------- | ------ | -------- | ------------------------------------------------------ |
| `pattern`  | string | Yes      | Glob pattern (e.g. `*.py`, `**/*.txt`)                 |
| `base_dir` | string | No       | Subdirectory to restrict the search to (default: root) |

**Returns:** Sorted list of matching file paths relative to the repository root. Empty list if no matches.

**Examples:**

```json
{"pattern": "**/*.py"}
{"pattern": "*.json", "base_dir": "config"}
```

---

### Git Tools

> Git tools require the `git` CLI on PATH and a `.git` directory in the repository root.

#### `git_log`

Retrieve recent Git commit history.

| Parameter   | Type    | Required | Description                                 |
| ----------- | ------- | -------- | ------------------------------------------- |
| `max_count` | integer | No       | Maximum commits to return (default 10)      |
| `file_path` | string  | No       | Only return commits that modified this file |

**Returns:** List of `{"hash", "author", "date", "message"}` commit objects.

**Examples:**

```json
{}
{"max_count": 5}
{"file_path": "src/main.py", "max_count": 3}
```

**Errors:**

- `GitNotAvailableError` — No `.git` directory or `git` CLI not found

---

#### `git_diff`

Show diffs between commits or the working tree.

| Parameter | Type   | Required | Description             |
| --------- | ------ | -------- | ----------------------- |
| `ref1`    | string | No       | First commit reference  |
| `ref2`    | string | No       | Second commit reference |

**Behavior:**

- No refs → diff of uncommitted working tree changes
- One ref (`ref1`) → diff between that ref and the working tree
- Two refs (`ref1`, `ref2`) → diff between the two commits

**Returns:** Diff text as a string (empty string if no differences).

**Examples:**

```json
{}
{"ref1": "HEAD~3"}
{"ref1": "abc1234", "ref2": "def5678"}
```

**Errors:**

- `GitRefNotFoundError` — Invalid commit reference
- `GitNotAvailableError` — No `.git` directory or `git` CLI not found

---

#### `git_status`

Return current branch and file status.

**Parameters:** None required.

**Returns:**

```json
{
  "branch": "main",
  "modified": ["file1.py"],
  "staged": ["file2.py"],
  "untracked": ["newfile.txt"]
}
```

---

#### `git_branches`

List local branches.

**Parameters:** None required.

**Returns:** List of `{"name": "...", "is_current": true|false}` branch objects. Exactly one branch will have `is_current: true`.

**Example response:**

```json
[
  { "name": "main", "is_current": true },
  { "name": "feature-x", "is_current": false }
]
```

---

### Search Tools

#### `grep_search`

Full-text search across repository files with context lines.

| Parameter         | Type    | Required | Description                                     |
| ----------------- | ------- | -------- | ----------------------------------------------- |
| `query`           | string  | Yes      | Text to search for                              |
| `include_pattern` | string  | No       | Glob pattern to filter which files are searched |
| `case_sensitive`  | boolean | No       | Case-sensitive search (default: true)           |

**Returns:** List of match objects:

```json
{
  "file": "src/main.py",
  "line_number": 42,
  "content": "    result = process(data)",
  "context_before": ["    # Process the input", "    data = load()"],
  "context_after": ["    return result", ""]
}
```

Each match includes up to 2 lines of context before and after. Returns an empty list if no matches. Binary files are automatically skipped.

**Examples:**

```json
{"query": "TODO"}
{"query": "import", "include_pattern": "*.py"}
{"query": "error", "case_sensitive": false}
```

## Architecture

### Project Structure

```
ContextServer/
├── server/
│   ├── __init__.py
│   ├── main.py              # Entry point, CLI arg parsing, server startup
│   ├── mcp_server.py        # MCP protocol handling (wraps mcp SDK)
│   ├── tool_registry.py     # Tool registration, manifest, dispatch + validation
│   └── path_utils.py        # Path resolution and containment security
├── tools/
│   ├── __init__.py
│   ├── filesystem_tools.py  # read_file, list_directory, search_files
│   ├── git_tools.py         # git_log, git_diff, git_status, git_branches
│   └── search_tools.py      # grep_search
├── client/
│   ├── __init__.py
│   └── cli.py               # Interactive MCP client REPL
├── tests/
│   ├── test_path_utils.py
│   ├── test_tool_registry.py
│   ├── test_filesystem_tools.py
│   ├── test_git_tools.py
│   ├── test_search_tools.py
│   └── test_main.py
├── data/
│   └── docs/                # Sample documentation directory
└── pyproject.toml
```

### How It Works

1. **Startup** — `main.py` parses CLI args, validates the repo root, registers all 8 tools into the `ToolRegistry`, and starts the MCP server on stdio transport.

2. **Tool Discovery** — When a client sends `tools/list`, the server returns a manifest with each tool's name, description, and JSON Schema for its parameters.

3. **Tool Invocation** — When a client sends `tools/call`, the server:
   - Looks up the tool in the registry
   - Validates parameters against the tool's JSON Schema
   - Dispatches to the async handler
   - Returns the result as MCP `TextContent`, or an error response if something fails

4. **Path Security** — Every filesystem operation passes through `resolve_and_validate()` which resolves symlinks via `os.path.realpath()` and verifies the result stays within the repo root.

5. **Git Operations** — Git tools shell out to the `git` CLI via `subprocess` rather than using a Python Git library, keeping dependencies minimal.

### Error Handling

All tool errors are caught and returned as MCP error responses (`isError: true`) with descriptive messages. The server never crashes from a tool error.

| Error Type               | When                                       |
| ------------------------ | ------------------------------------------ |
| `ToolNotFoundError`      | Unknown tool name in `tools/call`          |
| `InvalidParametersError` | Parameters fail JSON Schema validation     |
| `FileNotFoundError`      | File or directory doesn't exist            |
| `PathContainmentError`   | Path resolves outside the repository root  |
| `GitNotAvailableError`   | No `.git` directory or `git` CLI not found |
| `GitRefNotFoundError`    | Invalid commit reference                   |

## MCP Integration

### Using with an MCP Client

ContextServer works with any MCP-compatible client. To configure it in an `mcp.json`:

```json
{
  "mcpServers": {
    "ContextServer": {
      "command": "python",
      "args": ["-m", "server.main", "--repo-root", "/path/to/your/repo"],
      "cwd": "/path/to/ContextServer"
    }
  }
}
```

### Using Programmatically

```python
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

params = StdioServerParameters(
    command="python",
    args=["-m", "server.main", "--repo-root", "/path/to/repo"],
    cwd="/path/to/ContextServer",
)

async with stdio_client(params) as (read, write):
    async with ClientSession(read, write) as session:
        await session.initialize()

        # List tools
        tools = await session.list_tools()

        # Read a file
        result = await session.call_tool("read_file", {"path": "README.md"})

        # Search for code
        result = await session.call_tool("grep_search", {
            "query": "def main",
            "include_pattern": "*.py"
        })
```

## Testing

Run the full test suite:

```bash
python -m pytest tests/ -v
```

The test suite includes 103 tests covering:

- **Path utils** (11 tests) — path resolution, containment, symlink handling, traversal prevention
- **Tool registry** (9 tests) — registration, manifest generation, dispatch, error handling
- **Filesystem tools** (29 tests) — read_file, list_directory, search_files with edge cases
- **Git tools** (31 tests) — git_log, git_diff, git_status, git_branches against temp repos
- **Search tools** (15 tests) — grep_search with context lines, patterns, case sensitivity
- **Main entry point** (8 tests) — argument parsing, repo root validation

### Running a Single Test Module

```bash
python -m pytest tests/test_filesystem_tools.py -v
python -m pytest tests/test_git_tools.py -v
```

## Security

- All file paths are resolved to absolute paths and verified against the repository root before any I/O
- Symlinks that resolve outside the repository root are rejected
- `../` traversal attempts are blocked
- The server operates in read-only mode — no write operations are exposed
- Git operations are scoped to the configured repository root

## License

MIT
