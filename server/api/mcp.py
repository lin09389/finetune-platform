from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

from mcp import MCPServerManager, MCPClient
from mcp.types import MCPServerInfo, MCPTool

router = APIRouter(prefix="/mcp", tags=["MCP - Model Context Protocol"])

_manager: Optional[MCPServerManager] = None


def get_manager() -> MCPServerManager:
    global _manager
    if _manager is None:
        _manager = MCPServerManager()
    return _manager


class AddServerRequest(BaseModel):
    name: str = Field(..., description="服务器名�?)
    transport: str = Field(..., description="传输类型：stdio �?sse")
    command: Optional[str] = Field(default=None, description="stdio 模式下的命令")
    args: Optional[List[str]] = Field(default=None, description="命令参数")
    url: Optional[str] = Field(default=None, description="sse 模式下的 URL")


class CallToolRequest(BaseModel):
    tool_name: str = Field(..., description="工具名称")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="工具参数")


class ToolResponse(BaseModel):
    name: str
    description: str
    input_schema: Dict[str, Any]


class ServerResponse(BaseModel):
    name: str
    transport: str
    status: str
    command: Optional[str] = None
    args: List[str] = []
    url: Optional[str] = None


class OverallStatusResponse(BaseModel):
    total_servers: int
    connected_servers: int
    disconnected_servers: int
    total_tools: int


@router.get("/tools")
async def list_tools():
    manager = get_manager()
    tools = await manager.list_all_tools()
    return {
        "tools": [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
                "server": manager.get_tool_server(tool.name)
            }
            for tool in tools
        ],
        "total": len(tools)
    }


@router.post("/call")
async def call_tool(request: CallToolRequest):
    manager = get_manager()
    if not manager.is_tool_available(request.tool_name):
        raise HTTPException(
            status_code=404,
            detail=f"Tool not found: {request.tool_name}"
        )
    result = await manager.call_tool(request.tool_name, request.arguments)
    return {
        "call_id": result.call_id,
        "content": result.content,
        "is_error": result.is_error,
        "tool_name": request.tool_name
    }


@router.get("/servers")
async def list_servers():
    manager = get_manager()
    all_info = manager.get_all_server_info()
    servers = []
    for name, info in all_info.items():
        servers.append({
            "name": info.name,
            "transport": info.transport,
            "status": manager.get_server_status(name),
            "command": info.command,
            "args": info.args,
            "url": info.url
        })
    return {
        "servers": servers,
        "total": len(servers)
    }


@router.post("/servers")
async def add_server(request: AddServerRequest):
    manager = get_manager()
    if request.transport not in ["stdio", "sse"]:
        raise HTTPException(
            status_code=400,
            detail="Transport must be 'stdio' or 'sse'"
        )
    if request.transport == "stdio" and not request.command:
        raise HTTPException(
            status_code=400,
            detail="Command is required for stdio transport"
        )
    if request.transport == "sse" and not request.url:
        raise HTTPException(
            status_code=400,
            detail="URL is required for sse transport"
        )
    server_info = MCPServerInfo(
        name=request.name,
        transport=request.transport,
        command=request.command,
        args=request.args or [],
        url=request.url
    )
    success = await manager.add_server(request.name, server_info)
    if not success:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to add server: {request.name}"
        )
    return {
        "status": "success",
        "message": f"Server '{request.name}' added successfully",
        "server": {
            "name": request.name,
            "transport": request.transport,
            "status": manager.get_server_status(request.name)
        }
    }


@router.delete("/servers/{name}")
async def remove_server(name: str):
    manager = get_manager()
    if manager.get_server_status(name) == "not_found":
        raise HTTPException(
            status_code=404,
            detail=f"Server not found: {name}"
        )
    await manager.remove_server(name)
    return {
        "status": "success",
        "message": f"Server '{name}' removed successfully"
    }


@router.get("/servers/{name}/status")
async def get_server_status(name: str):
    manager = get_manager()
    status = manager.get_server_status(name)
    if status == "not_found":
        raise HTTPException(
            status_code=404,
            detail=f"Server not found: {name}"
        )
    info = manager.get_server_info(name)
    return {
        "name": name,
        "status": status,
        "transport": info.transport if info else None,
        "command": info.command if info else None,
        "args": info.args if info else [],
        "url": info.url if info else None
    }


@router.post("/servers/{name}/reconnect")
async def reconnect_server(name: str):
    manager = get_manager()
    if manager.get_server_status(name) == "not_found":
        raise HTTPException(
            status_code=404,
            detail=f"Server not found: {name}"
        )
    success = await manager.reconnect_server(name)
    if not success:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reconnect server: {name}"
        )
    return {
        "status": "success",
        "message": f"Server '{name}' reconnected successfully",
        "server_status": manager.get_server_status(name)
    }


@router.get("/servers/{name}/tools")
async def get_server_tools(name: str):
    manager = get_manager()
    if manager.get_server_status(name) == "not_found":
        raise HTTPException(
            status_code=404,
            detail=f"Server not found: {name}"
        )
    tool_names = manager.get_tools_by_server(name)
    all_tools = await manager.list_all_tools()
    tools = [t for t in all_tools if t.name in tool_names]
    return {
        "server_name": name,
        "tools": [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema
            }
            for tool in tools
        ],
        "total": len(tools)
    }


@router.get("/status")
async def get_overall_status():
    manager = get_manager()
    return {
        "total_servers": manager.get_server_count(),
        "connected_servers": len(manager.get_connected_servers()),
        "disconnected_servers": len(manager.get_disconnected_servers()),
        "total_tools": manager.get_tool_count(),
        "connected_server_names": manager.get_connected_servers(),
        "disconnected_server_names": manager.get_disconnected_servers()
    }
