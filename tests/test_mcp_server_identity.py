"""MCP application identity, with no provider tool calls or user configuration."""
from __future__ import annotations

import asyncio
import builtins
import os
import socket
from pathlib import Path
import sys
import runpy

import pytest

from research_hub import __version__


_CHILD_SOCKET_FENCE = (
    "import pytest_socket; "
    "pytest_socket.socket_allow_hosts(['127.0.0.1', '::1'], allow_unix_socket=True); "
)


def test_fallback_preserves_application_version():
    from research_hub.mcp_server import _FallbackMCP

    server = _FallbackMCP("research-hub", version=__version__)
    assert server.version == __version__


def test_child_socket_fence_allows_loopback_and_blocks_external(monkeypatch):
    # Windows asyncio uses a loopback TCP pair for its self-pipe. Exercise the
    # exact child bootstrap rather than relying on the parent's autouse fence.
    namespace = {}
    exec(_CHILD_SOCKET_FENCE, namespace)
    pytest_socket = namespace["pytest_socket"]

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.settimeout(2)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        with socket.create_connection(listener.getsockname(), timeout=2):
            connection, _ = listener.accept()
            connection.close()

    # The guard must reject external addresses before the underlying connect.
    # A fail-fast sentinel prevents external I/O even if the guard regresses.
    def unexpected_connect(*_args):
        pytest.fail("external address reached the underlying socket connect")

    with monkeypatch.context() as patch:
        patch.setattr(pytest_socket, "_true_connect", unexpected_connect)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as external:
            with pytest.raises(pytest_socket.SocketConnectBlockedError):
                external.connect(("192.0.2.1", 443))
        if socket.has_ipv6:
            with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as external:
                with pytest.raises(pytest_socket.SocketConnectBlockedError):
                    external.connect(("2001:db8::1", 443))


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
            _CHILD_SOCKET_FENCE
            + "import runpy; "
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
