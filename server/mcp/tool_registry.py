import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any

from mcp.server_manager import get_mcp_server_manager
from mcp.types import MCPTool, MCPToolResult


@dataclass
class MCPToolParameter:
    name: str
    type: str
    description: str = ""
    required: bool = False
    default: Any = None
    enum_values: list[Any] | None = None
    min_value: int | float | None = None
    max_value: int | float | None = None


@dataclass
class MCPToolMetadata:
    name: str
    display_name: str
    description: str
    version: str
    category: str
    tags: list[str]
    parameters: list[MCPToolParameter]


@dataclass
class RegisteredTool:
    tool: MCPTool
    server_name: str
    metadata: MCPToolMetadata
    last_used: float | None = None
    use_count: int = 0
    cache_enabled: bool = True
    average_duration_ms: float = 0.0


class MCPToolRegistry:
    def __init__(self, server_manager=None):
        self._server_manager = server_manager
        self._registered_tools: dict[str, RegisteredTool] = {}
        self._tool_cache: dict[str, tuple] = {}
        self._cache_ttl: int = 300

    @property
    def server_manager(self):
        if self._server_manager is None:
            self._server_manager = get_mcp_server_manager()
        return self._server_manager

    def register_tool(self, tool: MCPTool, server_name: str) -> bool:
        if tool.name in self._registered_tools:
            return False

        metadata = self.create_tool_metadata(tool, server_name)

        self._registered_tools[tool.name] = RegisteredTool(
            tool=tool,
            server_name=server_name,
            metadata=metadata,
        )
        return True

    def unregister_tool(self, tool_name: str) -> bool:
        if tool_name not in self._registered_tools:
            return False

        del self._registered_tools[tool_name]
        self.clear_cache(tool_name)
        return True

    def get_tool(self, tool_name: str) -> RegisteredTool | None:
        return self._registered_tools.get(tool_name)

    def list_tools(self) -> list[RegisteredTool]:
        return list(self._registered_tools.values())

    def list_tools_by_server(self, server_name: str) -> list[RegisteredTool]:
        return [
            t for t in self._registered_tools.values()
            if t.server_name == server_name
        ]

    def create_tool_metadata(self, tool: MCPTool, server_name: str) -> MCPToolMetadata:
        return MCPToolMetadata(
            name=tool.name,
            display_name=tool.name.replace("_", " ").title(),
            description=tool.description,
            version="1.0.0",
            category="extension",
            tags=["mcp", "external", server_name],
            parameters=self._convert_schema_to_parameters(tool.input_schema),
        )

    def _convert_schema_to_parameters(
        self,
        input_schema: dict[str, Any]
    ) -> list[MCPToolParameter]:
        parameters = []

        if not input_schema:
            return parameters

        properties = input_schema.get("properties", {})
        required = input_schema.get("required", [])

        for name, schema in properties.items():
            param_type = self._infer_parameter_type(
                schema.get("type", "string"),
                schema
            )

            parameters.append(MCPToolParameter(
                name=name,
                type=param_type,
                description=schema.get("description", ""),
                required=name in required,
                default=schema.get("default"),
                enum_values=schema.get("enum"),
                min_value=schema.get("minimum"),
                max_value=schema.get("maximum"),
            ))

        return parameters

    def _infer_parameter_type(
        self,
        json_type: str,
        schema: dict[str, Any]
    ) -> str:
        type_mapping = {
            "string": "string",
            "integer": "integer",
            "number": "float",
            "boolean": "boolean",
            "array": "array",
            "object": "object",
        }

        if "enum" in schema:
            return "enum"

        return type_mapping.get(json_type, "string")

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        use_cache: bool = True
    ) -> MCPToolResult:
        registered = self._registered_tools.get(tool_name)
        if not registered:
            return MCPToolResult(
                call_id="",
                content=f"Tool not found: {tool_name}",
                is_error=True,
            )

        cache_key = self.get_cache_key(tool_name, arguments)

        if use_cache and registered.cache_enabled and cache_key in self._tool_cache:
            cached_result, cached_time = self._tool_cache[cache_key]
            if time.time() - cached_time < self._cache_ttl:
                registered.use_count += 1
                return cached_result

        start_time = time.time()

        try:
            result = await self.server_manager.call_tool(tool_name, arguments)
        except Exception as e:
            return MCPToolResult(
                call_id="",
                content=str(e),
                is_error=True,
            )

        duration_ms = (time.time() - start_time) * 1000

        registered.last_used = time.time()
        registered.use_count += 1
        registered.average_duration_ms = (
            (registered.average_duration_ms * (registered.use_count - 1) + duration_ms)
            / registered.use_count
        )

        if use_cache and registered.cache_enabled:
            self._tool_cache[cache_key] = (result, time.time())

        return result

    def get_cache_key(
        self,
        tool_name: str,
        arguments: dict[str, Any]
    ) -> str:
        args_str = json.dumps(arguments, sort_keys=True, ensure_ascii=False)
        args_hash = hashlib.md5(args_str.encode()).hexdigest()
        return f"{tool_name}:{args_hash}"

    def clear_cache(self, tool_name: str | None = None) -> None:
        if tool_name:
            keys_to_remove = [
                k for k in self._tool_cache
                if k.startswith(f"{tool_name}:")
            ]
            for key in keys_to_remove:
                del self._tool_cache[key]
        else:
            self._tool_cache.clear()

    def get_tool_stats(self, tool_name: str) -> dict[str, Any]:
        registered = self._registered_tools.get(tool_name)
        if not registered:
            return {}

        return {
            "tool_name": tool_name,
            "server_name": registered.server_name,
            "use_count": registered.use_count,
            "last_used": registered.last_used,
            "average_duration_ms": registered.average_duration_ms,
            "cache_enabled": registered.cache_enabled,
        }

    async def discover_and_register_tools(self, server_name: str) -> int:
        tools = await self.server_manager.list_all_tools()

        count = 0
        for tool in tools:
            tool_server = self.server_manager.get_tool_server(tool.name)
            if tool_server == server_name and self.register_tool(tool, server_name):
                count += 1

        return count

    async def refresh_all_tools(self) -> dict[str, int]:
        results = {}

        self._registered_tools.clear()
        self.clear_cache()

        tools = await self.server_manager.list_all_tools()

        for tool in tools:
            server_name = self.server_manager.get_tool_server(tool.name)
            if server_name and self.register_tool(tool, server_name):
                results[server_name] = results.get(server_name, 0) + 1

        return results

    def get_all_metadata(self) -> list[MCPToolMetadata]:
        return [registered.metadata for registered in self._registered_tools.values()]


_mcp_tool_registry: MCPToolRegistry | None = None


def get_mcp_tool_registry() -> MCPToolRegistry:
    global _mcp_tool_registry
    if _mcp_tool_registry is None:
        _mcp_tool_registry = MCPToolRegistry()
    return _mcp_tool_registry


def reset_mcp_tool_registry() -> MCPToolRegistry:
    global _mcp_tool_registry
    _mcp_tool_registry = MCPToolRegistry()
    return _mcp_tool_registry


def create_mcp_tool_metadata(
    tool: MCPTool,
    server_name: str,
    server_manager=None
) -> MCPToolMetadata:
    registry = MCPToolRegistry(server_manager)
    return registry.create_tool_metadata(tool, server_name)
