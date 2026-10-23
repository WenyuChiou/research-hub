"""MCP application identity, with no provider tool calls or user configuration."""
from __future__ import annotations

import asyncio
import builtins
import os
from pathlib import Path
import sys
import runpy

import pytest

from research_hub import __version__


def test_fallback_preserves_application_version():
    from research_hub.mcp_server import _FallbackMCP

    server = _FallbackMCP("research-hub", version=__version__)
    assert server.version == __version__


def test_stdio_initialize_reports_application_version(tmp_path):
    pytest.importorskip("fastmcp")
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    # Only local stdio protocol operations: never call a registered tool.
    # Fence the child as well as pytest's parent; prevent private config reads.
    source = Path(__file__).resolve().parents[1] / "src"
    env = {
        "PATH": os.defpath,
        "HOME": str(tmp_path),
        "USERPROFILE": str(tmp_path),
        "APPDATA": str(tmp_path),
        "LOCALAPPDATA": str(tmp_path),
        "XDG_CONFIG_HOME": str(tmp_path),
        "XDG_CACHE_HOME": str(tmp_path),
        "RESEARCH_HUB_CONFIG": str(tmp_path / "absent-config.json"),
        "RESEARCH_HUB_ROOT": str(tmp_path),
        "PYTHONPATH": str(source),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FASTMCP_CHECK_FOR_UPDATES": "off",
    }
    if "SYSTEMROOT" in os.environ:
        env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-c", (
            "import pytest_socket, runpy; "
            "pytest_socket.disable_socket(allow_unix_socket=True); "
            "runpy.run_module('research_hub.mcp_server', run_name='__main__')"
        )],
        env=env,
        cwd=tmp_path,
    )

    async def exchange():
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as session:
                initialized = await session.initialize()
                tools = await session.list_tools()
                return initialized.server_info, {tool.name for tool in tools.tools}

    # Context managers close stdin and reap the server even on failure/timeout.
    info, tools = asyncio.run(asyncio.wait_for(exchange(), timeout=20))
    assert info.name == "research-hub"
    assert tools, "tools/list must remain available"
    assert "workspace_project" in tools
    assert info.version == __version__, (info.version, __version__)


def test_server_import_without_optional_fastmcp(monkeypatch):
    real_import = builtins.__import__

    def without_fastmcp(name, *args, **kwargs):
        if name == "fastmcp" or name.startswith("fastmcp."):
            raise ImportError("optional dependency deliberately absent")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_fastmcp)
    source = Path(__file__).resolve().parents[1] / "src/research_hub/mcp_server.py"
    namespace = runpy.run_path(str(source), run_name="identity_fallback_probe")
    assert namespace["FastMCP"] is None
    assert namespace["mcp"].version == __version__
    assert "workspace_project" in namespace["mcp"]._tool_manager._tools
    with pytest.raises(RuntimeError, match="fastmcp is not installed"):
        namespace["mcp"].run()
