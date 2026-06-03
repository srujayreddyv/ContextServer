# ContextServer: High-Level Project Description

ContextServer is a local MCP-based tool infrastructure project that gives AI agents safe, structured access to real codebase context. It exposes read-only filesystem tools, Git repository introspection, documentation search, and a local web dashboard through the Model Context Protocol.

The project demonstrates how an AI agent can move beyond plain chat and interact with real developer workflows through well-defined, schema-validated tools. Instead of giving an agent broad, unsafe access to a machine, ContextServer provides a controlled interface for reading files, listing directories, searching code and documentation, and inspecting Git state.

## What It Does

ContextServer runs as a Python MCP server over stdio, the transport commonly used by local MCP clients. AI clients can discover available tools through `tools/list` and invoke them through `tools/call`.

The built-in tools support:

- Reading files and line ranges inside a configured repository root.
- Listing directories with bounded recursion.
- Searching files by glob pattern.
- Searching code or text with grep-style matching.
- Searching documentation-focused files such as Markdown, MDX, text, and reStructuredText.
- Inspecting Git history, diffs, branches, and working tree status.

The project also includes a local browser dashboard that acts as an MCP workbench. Users can inspect the built-in ContextServer tools, call tools with JSON arguments, and register other stdio MCP servers for manual testing.

## Why It Matters

The significance of ContextServer is not that it replaces mature MCP servers. Its value is that it shows a from-scratch understanding of the infrastructure layer behind AI agents:

- How MCP servers expose capabilities to AI clients.
- How tool discovery and invocation work.
- How to design schema-validated tool interfaces.
- How to route tool calls through an extensible registry.
- How to constrain filesystem access with path containment.
- How to integrate Git safely through read-only subprocess calls.
- How to test agent-facing infrastructure end to end.

For hiring managers, this project signals practical experience building the boundary between AI systems and real developer environments. It shows the ability to design safe, testable, extensible infrastructure for AI-assisted software engineering workflows.

## Architecture

ContextServer is organized around a small MCP server, an internal plugin-style tool registry, and grouped tool modules.

At a high level:

```text
MCP Client / Local Web Dashboard
        |
        | stdio MCP transport
        v
ContextServer
        |
        v
ToolRegistry
        |
        +-- Filesystem tools
        +-- Git tools
        +-- Search tools
        +-- Documentation tools
```

The MCP routing layer does not need to know the details of each tool. Tools are registered through internal plugin modules, which makes it straightforward to add new capabilities without modifying the core MCP request handling code.

## Safety and Scope

ContextServer is intentionally read-only. It does not expose file editing, deletion, or command execution tools. Filesystem operations are constrained to a configured repository root, and path resolution follows symlinks before enforcing containment.

This makes the project suitable as a safe local context provider for AI agents and as a demonstration of responsible tool design.

## Technical Highlights

- Python MCP server using the official `mcp` SDK.
- JSON Schema validation for every tool call.
- Internal plugin-style registration for tool groups.
- Documentation-specific search tool.
- Local browser dashboard for MCP server and tool exploration.
- End-to-end MCP stdio integration tests.
- Full automated test suite covering filesystem safety, Git behavior, search behavior, docs search, plugin registration, and web UI helpers.

## How To Describe It

Resume-friendly summary:

> Built a local MCP-based tool server enabling AI agents to inspect codebases through read-only filesystem access, Git repository introspection, and documentation search. Architected an internal plugin-style tool registry with schema-validated tool definitions, allowing new capabilities to be added without modifying core MCP routing. Added a local web dashboard for exploring and testing ContextServer and other stdio MCP servers.

Short version:

> ContextServer is a local MCP workbench and tool server that gives AI agents safe, read-only access to repository context through filesystem, Git, search, and documentation tools.
