"""Godot Engine adapter for DCC-MCP."""

from .__version__ import __version__
from .server import GodotMcpServer, start_server, stop_server

__all__ = ["GodotMcpServer", "__version__", "start_server", "stop_server"]
