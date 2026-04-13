"""Test helpers that work across fastmcp versions.

fastmcp changed internal tool storage between minor releases. The public API
is ``mcp.get_tools()`` (async, returns a dict keyed by tool name). Older
versions exposed ``mcp._tool_manager._tools``. These helpers try the public
API first, then fall back to the private one so tests pass regardless of
which fastmcp version CI happens to resolve.
"""

from __future__ import annotations

import asyncio


def _resolve(value):
    if hasattr(value, "__await__"):
        return asyncio.run(value)
    return value


def _list_mcp_tool_names(mcp_instance) -> set[str]:
    """Return registered MCP tool names across fastmcp versions."""
    get_tools = getattr(mcp_instance, "get_tools", None)
    if callable(get_tools):
        try:
            result = _resolve(get_tools())
            if isinstance(result, dict):
                return set(result.keys())
            if result:
                return {getattr(tool, "name", None) for tool in result if getattr(tool, "name", None)}
        except Exception:
            pass

    tm = getattr(mcp_instance, "_tool_manager", None)
    if tm is not None:
        tools_attr = getattr(tm, "_tools", None)
        if isinstance(tools_attr, dict):
            return set(tools_attr.keys())

    list_tools = getattr(mcp_instance, "list_tools", None)
    if callable(list_tools):
        try:
            result = _resolve(list_tools())
            if isinstance(result, dict):
                return set(result.keys())
            return {getattr(tool, "name", None) for tool in result if getattr(tool, "name", None)}
        except Exception:
            pass

    return set()


def _get_mcp_tool(mcp_instance, name: str):
    """Return a tool wrapper with a ``.fn`` attribute across fastmcp versions."""
    get_tool = getattr(mcp_instance, "get_tool", None)
    if callable(get_tool):
        try:
            result = _resolve(get_tool(name))
            if result is not None:
                return result
        except Exception:
            pass

    get_tools = getattr(mcp_instance, "get_tools", None)
    if callable(get_tools):
        try:
            result = _resolve(get_tools())
            if isinstance(result, dict) and name in result:
                return result[name]
        except Exception:
            pass

    tm = getattr(mcp_instance, "_tool_manager", None)
    if tm is not None:
        tools_attr = getattr(tm, "_tools", None)
        if isinstance(tools_attr, dict) and name in tools_attr:
            return tools_attr[name]

    return None
