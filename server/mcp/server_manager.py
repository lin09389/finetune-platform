from typing import Any, Optional

from .client import MCPClient
from .types import MCPServerInfo, MCPTool, MCPToolResult


class MCPServerManager:
    def __init__(self):
        self._servers: dict[str, MCPClient] = {}
        self._tool_to_server: dict[str, str] = {}
        self._server_configs: dict[str, MCPServerInfo] = {}

    async def add_server(self, name: str, server_info: MCPServerInfo) -> bool:
        if name in self._servers:
            return False
        client = MCPClient(server_info)
        if await client.connect():
            self._servers[name] = client
            self._server_configs[name] = server_info
            tools = await client.list_tools()
            for tool in tools:
                self._tool_to_server[tool.name] = name
            return True
        return False

    async def remove_server(self, name: str) -> None:
        if name in self._servers:
            await self._servers[name].disconnect()
            del self._servers[name]
            if name in self._server_configs:
                del self._server_configs[name]
            self._tool_to_server = {
                k: v for k, v in self._tool_to_server.items() if v != name
            }

    async def reconnect_server(self, name: str) -> bool:
        if name not in self._server_configs:
            return False
        if name in self._servers:
            await self._servers[name].disconnect()
            del self._servers[name]
        self._tool_to_server = {
            k: v for k, v in self._tool_to_server.items() if v != name
        }
        server_info = self._server_configs[name]
        return await self.add_server(name, server_info)

    async def list_all_tools(self) -> list[MCPTool]:
        tools = []
        for client in self._servers.values():
            tools.extend(await client.list_tools())
        return tools

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any]
    ) -> MCPToolResult:
        if tool_name not in self._tool_to_server:
            return MCPToolResult(
                call_id="",
                content=f"Tool not found: {tool_name}",
                is_error=True
            )
        server_name = self._tool_to_server[tool_name]
        client = self._servers[server_name]
        return await client.call_tool(tool_name, arguments)

    def get_server_status(self, name: str) -> str:
        if name in self._servers:
            if self._servers[name].is_connected:
                return "connected"
            return "disconnected"
        return "not_found"

    def get_server_names(self) -> list[str]:
        return list(self._servers.keys())

    def get_server_info(self, name: str) -> MCPServerInfo | None:
        return self._server_configs.get(name)

    def get_all_server_info(self) -> dict[str, MCPServerInfo]:
        return self._server_configs.copy()

    def get_tool_server(self, tool_name: str) -> str | None:
        return self._tool_to_server.get(tool_name)

    def get_tools_by_server(self, server_name: str) -> list[str]:
        return [
            tool_name
            for tool_name, srv_name in self._tool_to_server.items()
            if srv_name == server_name
        ]

    async def disconnect_all(self) -> None:
        for name in list(self._servers.keys()):
            await self.remove_server(name)

    def get_server_count(self) -> int:
        return len(self._servers)

    def get_tool_count(self) -> int:
        return len(self._tool_to_server)

    def is_tool_available(self, tool_name: str) -> bool:
        return tool_name in self._tool_to_server

    def get_connected_servers(self) -> list[str]:
        return [
            name for name, client in self._servers.items()
            if client.is_connected
        ]

    def get_disconnected_servers(self) -> list[str]:
        return [
            name for name, client in self._servers.items()
            if not client.is_connected
        ]


_mcp_server_manager: Optional["MCPServerManager"] = None


def get_mcp_server_manager() -> MCPServerManager:
    global _mcp_server_manager
    if _mcp_server_manager is None:
        _mcp_server_manager = MCPServerManager()
    return _mcp_server_manager


def reset_mcp_server_manager() -> MCPServerManager:
    global _mcp_server_manager
    _mcp_server_manager = MCPServerManager()
    return _mcp_server_manager
