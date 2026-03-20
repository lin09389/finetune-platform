# MCP (Model Context Protocol) 集成指南

## 概述

MCP 是一个标准化协议，用于连接外部工具服务器，扩展 AI 应用的能力。本指南介绍如何在 finetune-platform 中集成和使用 MCP 工具。

## 架构

```
┌─────────────────┐     MCP Protocol     ┌─────────────────┐
│                 │ ◄──────────────────► │                 │
│  finetune-      │                      │  MCP Server     │
│  platform       │     stdio / SSE      │  (External)     │
│                 │ ◄──────────────────► │                 │
└─────────────────┘                      └─────────────────┘
```

## 快速开始

### 1. 添加 MCP 服务器

```python
from mcp import MCPServerManager, MCPServerInfo

manager = MCPServerManager()

# 添加 stdio 传输的服务器
server_info = MCPServerInfo(
    name="filesystem",
    transport="stdio",
    command="npx",
    args=["-y", "@modelcontextprotocol/server-filesystem", "/path/to/files"]
)

success = await manager.add_server("filesystem", server_info)
if success:
    print("服务器连接成功")
```

### 2. 列出可用工具

```python
# 列出所有工具
tools = await manager.list_all_tools()
for tool in tools:
    print(f"工具: {tool.name}")
    print(f"描述: {tool.description}")
    print(f"参数: {tool.input_schema}")
```

### 3. 调用工具

```python
# 调用工具
result = await manager.call_tool(
    tool_name="read_file",
    arguments={"path": "/path/to/file.txt"}
)

if result.is_error:
    print(f"错误: {result.content}")
else:
    print(f"结果: {result.content}")
```

## 传输类型

### stdio 传输

通过标准输入/输出与本地进程通信：

```python
server_info = MCPServerInfo(
    name="my-server",
    transport="stdio",
    command="python",
    args=["-m", "my_mcp_server"]
)
```

### SSE 传输

通过 Server-Sent Events 与远程服务器通信：

```python
server_info = MCPServerInfo(
    name="remote-server",
    transport="sse",
    url="http://localhost:8080/sse"
)
```

## API 端点

### 列出所有 MCP 工具

```bash
GET /mcp/tools
```

响应：
```json
{
  "tools": [
    {
      "name": "read_file",
      "description": "读取文件内容",
      "input_schema": {
        "type": "object",
        "properties": {
          "path": {"type": "string", "description": "文件路径"}
        },
        "required": ["path"]
      },
      "server_name": "filesystem"
    }
  ]
}
```

### 调用 MCP 工具

```bash
POST /mcp/call
Content-Type: application/json

{
  "tool_name": "read_file",
  "arguments": {
    "path": "/path/to/file.txt"
  }
}
```

响应：
```json
{
  "call_id": "123",
  "content": "文件内容...",
  "is_error": false
}
```

### 添加 MCP 服务器

```bash
POST /mcp/servers
Content-Type: application/json

{
  "name": "filesystem",
  "transport": "stdio",
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path"]
}
```

### 获取服务器状态

```bash
GET /mcp/servers/{name}/status
```

响应：
```json
{
  "name": "filesystem",
  "status": "connected",
  "tool_count": 5
}
```

## 工具注册表

MCP 工具可以自动转换为 Skills：

```python
from mcp.tool_registry import get_mcp_tool_registry

registry = get_mcp_tool_registry()

# 发现并注册工具
count = await registry.discover_and_register_tools("filesystem")
print(f"注册了 {count} 个工具")

# 获取 Skill 类
skill_classes = registry.get_all_skill_classes()
for name, skill_class in skill_classes.items():
    print(f"Skill: {name}")

# 调用工具（带缓存）
result = await registry.call_tool(
    tool_name="read_file",
    arguments={"path": "/path/to/file.txt"},
    use_cache=True
)
```

## 创建自定义 MCP 服务器

### Python 示例

```python
import asyncio
import json
import sys

async def main():
    # 初始化
    init_request = await read_request()
    send_response({
        "jsonrpc": "2.0",
        "id": init_request["id"],
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {}
            },
            "serverInfo": {
                "name": "my-mcp-server",
                "version": "1.0.0"
            }
        }
    })
    
    # 处理请求
    while True:
        request = await read_request()
        
        if request["method"] == "tools/list":
            send_response({
                "jsonrpc": "2.0",
                "id": request["id"],
                "result": {
                    "tools": [
                        {
                            "name": "hello",
                            "description": "打招呼",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "name": {
                                        "type": "string",
                                        "description": "名字"
                                    }
                                },
                                "required": ["name"]
                            }
                        }
                    ]
                }
            })
        
        elif request["method"] == "tools/call":
            tool_name = request["params"]["name"]
            arguments = request["params"]["arguments"]
            
            if tool_name == "hello":
                result = f"Hello, {arguments['name']}!"
                send_response({
                    "jsonrpc": "2.0",
                    "id": request["id"],
                    "result": {
                        "content": result
                    }
                })

async def read_request():
    line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
    return json.loads(line)

def send_response(response):
    print(json.dumps(response), flush=True)

if __name__ == "__main__":
    asyncio.run(main())
```

## 常用 MCP 服务器

### 文件系统

```bash
npx -y @modelcontextprotocol/server-filesystem /path/to/files
```

### GitHub

```bash
npx -y @modelcontextprotocol/server-github
# 需要设置 GITHUB_TOKEN 环境变量
```

### PostgreSQL

```bash
npx -y @modelcontextprotocol/server-postgres "postgresql://user:pass@localhost/db"
```

### Puppeteer (浏览器自动化)

```bash
npx -y @modelcontextprotocol/server-puppeteer
```

## 缓存机制

工具注册表支持结果缓存：

```python
# 启用缓存（默认）
result = await registry.call_tool("tool_name", args, use_cache=True)

# 禁用缓存
result = await registry.call_tool("tool_name", args, use_cache=False)

# 清除特定工具的缓存
registry.clear_cache("tool_name")

# 清除所有缓存
registry.clear_cache()
```

## 错误处理

```python
from mcp import MCPClient

try:
    result = await manager.call_tool("tool_name", args)
    if result.is_error:
        print(f"工具调用失败: {result.content}")
except Exception as e:
    print(f"连接错误: {e}")
```

## 最佳实践

1. **使用缓存**：对于频繁调用的工具，启用缓存减少延迟
2. **错误处理**：始终检查 `is_error` 标志
3. **超时设置**：为长时间运行的操作设置超时
4. **资源清理**：使用完毕后断开服务器连接
5. **权限控制**：限制 MCP 服务器的访问范围

## 故障排除

### 连接失败
- 检查命令路径是否正确
- 确保依赖已安装
- 查看服务器日志

### 工具调用超时
- 增加超时时间
- 检查服务器是否响应
- 查看服务器资源使用情况

### 参数验证失败
- 检查参数类型是否匹配
- 确保必填参数已提供
- 参考 `input_schema` 验证参数
