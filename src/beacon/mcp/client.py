"""Beacon Command — MCP Client Adapter.

Provides a unified interface for agents to invoke MCP tools across all servers.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Optional

from beacon.logging import get_logger

logger = get_logger(__name__)


class MCPToolResult:
    """Result from an MCP tool invocation."""

    def __init__(
        self,
        tool_name: str,
        server: str,
        result: Any,
        latency_ms: int,
        success: bool,
        error: Optional[str] = None,
    ):
        self.tool_name = tool_name
        self.server = server
        self.result = result
        self.latency_ms = latency_ms
        self.success = success
        self.error = error


class MCPClientAdapter:
    """Unified MCP client for all Beacon MCP servers.

    Provides direct in-process tool invocation when servers are co-located,
    with fallback to HTTP SSE transport for remote servers.
    """

    def __init__(self) -> None:
        self._tool_registry: dict[str, tuple[str, Any]] = {}
        self._initialized = False

    def _ensure_initialized(self) -> None:
        """Lazy-initialize the tool registry from all MCP servers."""
        if self._initialized:
            return

        try:
            from beacon.mcp.hazard_server import mcp as hazard_mcp
            from beacon.mcp.geospatial_server import mcp as geo_mcp
            from beacon.mcp.resource_server import mcp as resource_mcp
            from beacon.mcp.operations_server import mcp as ops_mcp
            from beacon.mcp.verification_server import mcp as verify_mcp

            # Register tools from each server
            for server_name, server_mcp in [
                ("hazard", hazard_mcp),
                ("geospatial", geo_mcp),
                ("resource", resource_mcp),
                ("operations", ops_mcp),
                ("verification", verify_mcp),
            ]:
                for tool in server_mcp._tool_manager._tools.values():
                    full_name = f"{server_name}.{tool.name}"
                    self._tool_registry[full_name] = (server_name, tool)
                    # Also register by short name
                    self._tool_registry[tool.name] = (server_name, tool)

            self._initialized = True
            logger.info("mcp_client_initialized", tool_count=len(self._tool_registry))

        except Exception as e:
            logger.error("mcp_client_init_error", error=str(e))

    def list_tools(self) -> list[dict[str, str]]:
        """List all available MCP tools."""
        self._ensure_initialized()
        tools = []
        seen = set()
        for name, (server, tool) in self._tool_registry.items():
            if "." in name and name not in seen:
                seen.add(name)
                tools.append({
                    "name": name,
                    "server": server,
                    "description": tool.description or "",
                })
        return tools

    async def invoke(
        self,
        tool_name: str,
        params: dict[str, Any],
        *,
        agent_id: Optional[str] = None,
        mission_id: Optional[uuid.UUID] = None,
    ) -> MCPToolResult:
        """Invoke an MCP tool by name.

        Args:
            tool_name: Tool name (short or fully qualified).
            params: Tool parameters.
            agent_id: Calling agent for audit.
            mission_id: Associated mission for audit.

        Returns:
            MCPToolResult with the tool output.
        """
        self._ensure_initialized()

        if tool_name not in self._tool_registry:
            return MCPToolResult(
                tool_name=tool_name,
                server="unknown",
                result=None,
                latency_ms=0,
                success=False,
                error=f"Tool not found: {tool_name}",
            )

        server_name, tool = self._tool_registry[tool_name]
        start = time.monotonic()

        try:
            # Direct in-process invocation
            result = await tool.fn(**params)
            latency_ms = int((time.monotonic() - start) * 1000)

            logger.debug(
                "mcp_tool_invoked",
                tool=tool_name,
                server=server_name,
                latency_ms=latency_ms,
                agent_id=agent_id,
            )

            return MCPToolResult(
                tool_name=tool_name,
                server=server_name,
                result=result,
                latency_ms=latency_ms,
                success=True,
            )

        except Exception as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            logger.error(
                "mcp_tool_error",
                tool=tool_name,
                server=server_name,
                error=str(e),
                latency_ms=latency_ms,
            )
            return MCPToolResult(
                tool_name=tool_name,
                server=server_name,
                result=None,
                latency_ms=latency_ms,
                success=False,
                error=str(e),
            )


# Singleton
mcp_client = MCPClientAdapter()
