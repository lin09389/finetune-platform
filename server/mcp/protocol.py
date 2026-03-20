from typing import Dict, Any, Tuple


class MCPProtocol:
    PROTOCOL_VERSION = "2024-11-05"
    CLIENT_NAME = "finetune-platform"
    CLIENT_VERSION = "1.0.0"

    @staticmethod
    def create_initialize_request() -> Dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": MCPProtocol.PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {
                    "name": MCPProtocol.CLIENT_NAME,
                    "version": MCPProtocol.CLIENT_VERSION
                }
            }
        }

    @staticmethod
    def create_initialized_notification() -> Dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        }

    @staticmethod
    def create_list_tools_request(request_id: int = 2) -> Dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/list"
        }

    @staticmethod
    def create_call_tool_request(
        tool_name: str,
        arguments: Dict[str, Any],
        call_id: str
    ) -> Dict[str, Any]:
        request_id = int(call_id) if call_id.isdigit() else hash(call_id) % 10000
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }

    @staticmethod
    def create_list_resources_request(request_id: int = 3) -> Dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "resources/list"
        }

    @staticmethod
    def create_read_resource_request(
        uri: str,
        request_id: int = 4
    ) -> Dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "resources/read",
            "params": {
                "uri": uri
            }
        }

    @staticmethod
    def create_list_prompts_request(request_id: int = 5) -> Dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "prompts/list"
        }

    @staticmethod
    def create_get_prompt_request(
        name: str,
        arguments: Dict[str, Any],
        request_id: int = 6
    ) -> Dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "prompts/get",
            "params": {
                "name": name,
                "arguments": arguments
            }
        }

    @staticmethod
    def parse_response(response: Dict[str, Any]) -> Tuple[bool, Any]:
        if "error" in response:
            return False, response["error"]
        return True, response.get("result")

    @staticmethod
    def is_response_valid(response: Dict[str, Any]) -> bool:
        return "jsonrpc" in response and "jsonrpc" == "2.0"

    @staticmethod
    def get_request_id(response: Dict[str, Any]) -> Any:
        return response.get("id")

    @staticmethod
    def create_error_response(
        request_id: Any,
        code: int,
        message: str,
        data: Any = None
    ) -> Dict[str, Any]:
        error_obj = {"code": code, "message": message}
        if data is not None:
            error_obj["data"] = data
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": error_obj
        }
