"""Compatibility shim across MCP SDK versions.

mcp >= 2.0 renamed ``FastMCP`` to ``MCPServer`` and moved it to
``mcp.server.mcpserver``. Both expose the same decorator/run API we use
(``@mcp.tool()``, ``mcp.run(transport=...)``, ``mcp.list_tools()``), so we import
whichever exists and alias it to ``MCPServer``.
"""

from __future__ import annotations

try:  # mcp >= 2.0
    from mcp.server.mcpserver import MCPServer
except ModuleNotFoundError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as MCPServer  # type: ignore

__all__ = ["MCPServer"]
