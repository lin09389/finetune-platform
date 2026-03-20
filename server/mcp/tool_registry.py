from typing import Dict, Any, List, Optional, Type
from dataclasses import dataclass
import asyncio
import hashlib
import json
import time

from mcp.types import MCPTool, MCPToolResult
from mcp.server_manager import get_mcp_server_manager
from skills.base import SkillBase
from skills.models import (
    SkillMetadata,
    SkillParameter,
    SkillParameterType,
    SkillCategory,
    SkillResult,
)


@dataclass
class RegisteredTool:
    tool: MCPTool
    server_name: str
    skill_class: Type[SkillBase]
    last_used: Optional[float] = None
    use_count: int = 0
    cache_enabled: bool = True
    average_duration_ms: float = 0.0


class MCPToolRegistry:
    def __init__(self, server_manager=None):
        self._server_manager = server_manager
        self._registered_tools: Dict[str, RegisteredTool] = {}
        self._tool_cache: Dict[str, tuple] = {}
        self._cache_ttl: int = 300

    @property
    def server_manager(self):
        if self._server_manager is None:
            self._server_manager = get_mcp_server_manager()
        return self._server_manager

    def register_tool(self, tool: MCPTool, server_name: str) -> bool:
        if tool.name in self._registered_tools:
            return False
        
        skill_class = self.create_skill_class(tool, server_name)
        
        self._registered_tools[tool.name] = RegisteredTool(
            tool=tool,
            server_name=server_name,
            skill_class=skill_class,
        )
        return True

    def unregister_tool(self, tool_name: str) -> bool:
        if tool_name not in self._registered_tools:
            return False
        
        del self._registered_tools[tool_name]
        self.clear_cache(tool_name)
        return True

    def get_tool(self, tool_name: str) -> Optional[RegisteredTool]:
        return self._registered_tools.get(tool_name)

    def list_tools(self) -> List[RegisteredTool]:
        return list(self._registered_tools.values())

    def list_tools_by_server(self, server_name: str) -> List[RegisteredTool]:
        return [
            t for t in self._registered_tools.values()
            if t.server_name == server_name
        ]

    def create_skill_class(self, tool: MCPTool, server_name: str) -> Type[SkillBase]:
        registry = self
        
        class MCPToolSkill(SkillBase):
            _tool_name = tool.name
            _server_name = server_name
            _tool_description = tool.description
            _input_schema = tool.input_schema
            
            @classmethod
            def get_metadata(cls) -> SkillMetadata:
                parameters = registry._convert_schema_to_parameters(
                    cls._input_schema
                )
                
                return SkillMetadata(
                    name=cls._tool_name,
                    display_name=cls._tool_name.replace("_", " ").title(),
                    description=cls._tool_description,
                    version="1.0.0",
                    category=SkillCategory.EXTENSION,
                    tags=["mcp", "external", cls._server_name],
                    parameters=parameters,
                )
            
            async def execute(self, **kwargs) -> SkillResult:
                try:
                    result = await registry.call_tool(
                        cls._tool_name,
                        kwargs,
                        use_cache=True
                    )
                    
                    if result.is_error:
                        return SkillResult(
                            success=False,
                            message=f"Tool call failed: {result.content}",
                            data=None,
                        )
                    
                    return SkillResult(
                        success=True,
                        message=f"Tool {cls._tool_name} executed successfully",
                        data=result.content,
                    )
                except Exception as e:
                    return SkillResult(
                        success=False,
                        message=f"Error calling tool: {str(e)}",
                        data=None,
                    )
        
        MCPToolSkill.__name__ = f"MCP_{tool.name}"
        return MCPToolSkill

    def _convert_schema_to_parameters(
        self,
        input_schema: Dict[str, Any]
    ) -> List[SkillParameter]:
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
            
            parameters.append(SkillParameter(
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
        schema: Dict[str, Any]
    ) -> SkillParameterType:
        type_mapping = {
            "string": SkillParameterType.STRING,
            "integer": SkillParameterType.INTEGER,
            "number": SkillParameterType.FLOAT,
            "boolean": SkillParameterType.BOOLEAN,
            "array": SkillParameterType.ARRAY,
            "object": SkillParameterType.OBJECT,
        }
        
        if "enum" in schema:
            return SkillParameterType.ENUM
        
        return type_mapping.get(json_type, SkillParameterType.STRING)

    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
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
        arguments: Dict[str, Any]
    ) -> str:
        args_str = json.dumps(arguments, sort_keys=True, ensure_ascii=False)
        args_hash = hashlib.md5(args_str.encode()).hexdigest()
        return f"{tool_name}:{args_hash}"

    def clear_cache(self, tool_name: Optional[str] = None) -> None:
        if tool_name:
            keys_to_remove = [
                k for k in self._tool_cache.keys()
                if k.startswith(f"{tool_name}:")
            ]
            for key in keys_to_remove:
                del self._tool_cache[key]
        else:
            self._tool_cache.clear()

    def get_tool_stats(self, tool_name: str) -> Dict[str, Any]:
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
            if tool_server == server_name:
                if self.register_tool(tool, server_name):
                    count += 1
        
        return count

    async def refresh_all_tools(self) -> Dict[str, int]:
        results = {}
        
        self._registered_tools.clear()
        self.clear_cache()
        
        tools = await self.server_manager.list_all_tools()
        
        for tool in tools:
            server_name = self.server_manager.get_tool_server(tool.name)
            if server_name:
                if self.register_tool(tool, server_name):
                    results[server_name] = results.get(server_name, 0) + 1
        
        return results

    def get_all_skill_classes(self) -> Dict[str, Type[SkillBase]]:
        return {
            name: registered.skill_class
            for name, registered in self._registered_tools.items()
        }

    def get_all_metadata(self) -> List[SkillMetadata]:
        return [
            registered.skill_class.get_metadata()
            for registered in self._registered_tools.values()
        ]


_mcp_tool_registry: Optional[MCPToolRegistry] = None


def get_mcp_tool_registry() -> MCPToolRegistry:
    global _mcp_tool_registry
    if _mcp_tool_registry is None:
        _mcp_tool_registry = MCPToolRegistry()
    return _mcp_tool_registry


def reset_mcp_tool_registry() -> MCPToolRegistry:
    global _mcp_tool_registry
    _mcp_tool_registry = MCPToolRegistry()
    return _mcp_tool_registry


def create_mcp_skill_class(
    tool: MCPTool,
    server_name: str,
    server_manager=None
) -> Type[SkillBase]:
    registry = MCPToolRegistry(server_manager)
    return registry.create_skill_class(tool, server_name)
