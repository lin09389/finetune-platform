import asyncio
import json
from typing import Dict, List, Optional, Any
from .types import MCPServerInfo, MCPTool, MCPToolResult
from .protocol import MCPProtocol


class MCPClient:
    def __init__(self, server_info: MCPServerInfo):
        self.server_info = server_info
        self._process: Optional[asyncio.subprocess.Process] = None
        self._tools: List[MCPTool] = []
        self._connected = False
        self._request_id = 0
        self._pending_requests: Dict[int, asyncio.Future] = {}
        self._reader_task: Optional[asyncio.Task] = None
        self._write_lock = asyncio.Lock()
        self._server_capabilities: Dict[str, Any] = {}

    async def connect(self) -> bool:
        if self.server_info.transport == "stdio":
            return await self._connect_stdio()
        elif self.server_info.transport == "sse":
            return await self._connect_sse()
        return False

    async def disconnect(self) -> None:
        self._connected = False
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None
        if self._process:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()
            except Exception:
                pass
            self._process = None
        self._pending_requests.clear()
        self._tools.clear()

    async def list_tools(self) -> List[MCPTool]:
        return self._tools.copy()

    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> MCPToolResult:
        if not self._connected:
            return MCPToolResult(
                call_id="",
                content="Client not connected",
                is_error=True
            )
        self._request_id += 1
        call_id = str(self._request_id)
        request = MCPProtocol.create_call_tool_request(
            tool_name, arguments, call_id
        )
        try:
            success, result = await self._send_request(request)
            if success:
                content = result.get("content", [])
                return MCPToolResult(
                    call_id=call_id,
                    content=content,
                    is_error=result.get("isError", False)
                )
            else:
                return MCPToolResult(
                    call_id=call_id,
                    content=result,
                    is_error=True
                )
        except Exception as e:
            return MCPToolResult(
                call_id=call_id,
                content=str(e),
                is_error=True
            )

    async def _connect_stdio(self) -> bool:
        try:
            if not self.server_info.command:
                return False
            self._process = await asyncio.create_subprocess_exec(
                self.server_info.command,
                *self.server_info.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            self._reader_task = asyncio.create_task(self._read_responses())
            init_request = MCPProtocol.create_initialize_request()
            success, result = await self._send_request(init_request)
            if not success:
                await self.disconnect()
                return False
            self._server_capabilities = result.get("capabilities", {})
            self._request_id += 1
            tools_request = MCPProtocol.create_list_tools_request(self._request_id)
            success, result = await self._send_request(tools_request)
            if success and result:
                tools_data = result.get("tools", [])
                self._tools = [
                    MCPTool(
                        name=tool.get("name", ""),
                        description=tool.get("description", ""),
                        input_schema=tool.get("inputSchema", {})
                    )
                    for tool in tools_data
                ]
            self._connected = True
            self.server_info.status = "connected"
            return True
        except Exception:
            await self.disconnect()
            return False

    async def _connect_sse(self) -> bool:
        return False

    async def _send_request(self, request: Dict[str, Any]) -> tuple:
        if not self._process or not self._process.stdin:
            return False, "Process not available"
        request_id = request.get("id")
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        if request_id is not None:
            self._pending_requests[request_id] = future
        async with self._write_lock:
            try:
                message = json.dumps(request) + "\n"
                self._process.stdin.write(message.encode())
                await self._process.stdin.drain()
                if request_id is None:
                    return True, None
                return await asyncio.wait_for(future, timeout=30.0)
            except asyncio.TimeoutError:
                if request_id in self._pending_requests:
                    del self._pending_requests[request_id]
                return False, "Request timeout"
            except Exception as e:
                if request_id in self._pending_requests:
                    del self._pending_requests[request_id]
                return False, str(e)

    async def _read_responses(self) -> None:
        if not self._process or not self._process.stdout:
            return
        try:
            while True:
                line = await self._process.stdout.readline()
                if not line:
                    break
                try:
                    response = json.loads(line.decode().strip())
                    request_id = response.get("id")
                    if request_id is not None and request_id in self._pending_requests:
                        future = self._pending_requests.pop(request_id)
                        if not future.done():
                            success, result = MCPProtocol.parse_response(response)
                            future.set_result((success, result))
                except json.JSONDecodeError:
                    continue
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def capabilities(self) -> Dict[str, Any]:
        return self._server_capabilities.copy()
