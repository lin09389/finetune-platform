"""
MCP 模块测试
"""

from mcp.protocol import MCPProtocol
from mcp.types import MCPMessageType, MCPServerInfo, MCPTool, MCPToolResult


class TestMCPProtocol:
    def test_create_initialize_request(self):
        request = MCPProtocol.create_initialize_request()

        assert request["jsonrpc"] == "2.0"
        assert request["method"] == "initialize"
        assert "params" in request
        assert request["params"]["protocolVersion"] == MCPProtocol.PROTOCOL_VERSION

    def test_create_list_tools_request(self):
        request = MCPProtocol.create_list_tools_request()

        assert request["jsonrpc"] == "2.0"
        assert request["method"] == "tools/list"

    def test_create_call_tool_request(self):
        request = MCPProtocol.create_call_tool_request(
            tool_name="test_tool",
            arguments={"arg1": "value1"},
            call_id="123"
        )

        assert request["jsonrpc"] == "2.0"
        assert request["method"] == "tools/call"
        assert request["params"]["name"] == "test_tool"
        assert request["params"]["arguments"] == {"arg1": "value1"}

    def test_parse_response_success(self):
        response = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"data": "success"}
        }

        success, result = MCPProtocol.parse_response(response)
        assert success is True
        assert result == {"data": "success"}

    def test_parse_response_error(self):
        response = {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32600, "message": "Invalid Request"}
        }

        success, error = MCPProtocol.parse_response(response)
        assert success is False
        assert "code" in error


class TestMCPTool:
    def test_tool_creation(self):
        tool = MCPTool(
            name="test_tool",
            description="A test tool",
            input_schema={
                "type": "object",
                "properties": {
                    "arg1": {"type": "string", "description": "First argument"}
                },
                "required": ["arg1"]
            }
        )

        assert tool.name == "test_tool"
        assert tool.description == "A test tool"
        assert "properties" in tool.input_schema


class TestMCPToolResult:
    def test_result_creation_success(self):
        result = MCPToolResult(
            call_id="123",
            content={"output": "success"},
            is_error=False
        )

        assert result.call_id == "123"
        assert result.is_error is False

    def test_result_creation_error(self):
        result = MCPToolResult(
            call_id="123",
            content="Error message",
            is_error=True
        )

        assert result.is_error is True


class TestMCPServerInfo:
    def test_server_info_stdio(self):
        info = MCPServerInfo(
            name="test_server",
            transport="stdio",
            command="python",
            args=["-m", "test_server"]
        )

        assert info.name == "test_server"
        assert info.transport == "stdio"
        assert info.command == "python"
        assert info.status == "disconnected"

    def test_server_info_sse(self):
        info = MCPServerInfo(
            name="test_server",
            transport="sse",
            url="http://localhost:8080/sse"
        )

        assert info.name == "test_server"
        assert info.transport == "sse"
        assert info.url == "http://localhost:8080/sse"


class TestMCPMessageType:
    def test_message_type_values(self):
        assert MCPMessageType.REQUEST.value == "request"
        assert MCPMessageType.RESPONSE.value == "response"
        assert MCPMessageType.NOTIFICATION.value == "notification"


class TestMCPServerManager:
    def test_manager_creation(self):
        from mcp.server_manager import MCPServerManager
        manager = MCPServerManager()
        assert manager.get_server_count() == 0

    def test_get_server_names(self):
        from mcp.server_manager import MCPServerManager
        manager = MCPServerManager()
        names = manager.get_server_names()
        assert isinstance(names, list)

    def test_get_tool_count(self):
        from mcp.server_manager import MCPServerManager
        manager = MCPServerManager()
        count = manager.get_tool_count()
        assert count == 0

    def test_is_tool_available(self):
        from mcp.server_manager import MCPServerManager
        manager = MCPServerManager()
        assert manager.is_tool_available("nonexistent_tool") is False

    def test_get_server_status(self):
        from mcp.server_manager import MCPServerManager
        manager = MCPServerManager()
        status = manager.get_server_status("nonexistent")
        assert status == "not_found"


class TestMCPToolRegistry:
    def test_registry_creation(self):
        from mcp.tool_registry import MCPToolRegistry
        registry = MCPToolRegistry()
        tools = registry.list_tools()
        assert isinstance(tools, list)

    def test_get_tool_stats(self):
        from mcp.tool_registry import MCPToolRegistry
        registry = MCPToolRegistry()
        stats = registry.get_tool_stats("nonexistent_tool")
        assert stats == {}

    def test_get_cache_key(self):
        from mcp.tool_registry import MCPToolRegistry
        registry = MCPToolRegistry()
        key = registry.get_cache_key("test_tool", {"arg": "value"})
        assert "test_tool:" in key
