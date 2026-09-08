"""Local researcher workspace, shared by CLI, HTTP and MCP transports."""

from .core import Workspace, WorkspaceError

__all__ = ["Workspace", "WorkspaceError"]
