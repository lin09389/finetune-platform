# 新模块集成规范文档

## 1. 概述

本文档描述了 CUA (Computer Use Agent) 和 MCP (Model Context Protocol) 模块与 Finetune Platform 的集成规范。

## 2. 模块架构

### 2.1 CUA 模块

```
server/cua/
├── __init__.py          # 模块入口，导出公共接口
├── config.py            # 配置管理
├── exceptions.py        # 异常定义
├── types.py             # 类型定义 (枚举等)
├── models.py            # Pydantic 数据模型
├── screen.py            # 屏幕截图
├── mouse.py             # 鼠标控制
├── keyboard.py          # 键盘控制
├── window.py            # 窗口管理
├── ocr.py               # OCR 识别
├── vision.py            # 视觉处理
├── recorder.py          # 操作录制
├── player.py            # 操作回放
└── safety.py            # 安全控制
```

### 2.2 MCP 模块

```
server/mcp/
├── __init__.py          # 模块入口
├── types.py             # 类型定义
├── protocol.py          # JSON-RPC 协议
├── client.py            # MCP 客户端
├── server_manager.py    # 服务器管理
└── tool_registry.py     # 工具注册与 Skill 转换
```

## 3. API 接口规范

### 3.1 CUA API 端点

| 端点 | 方法 | 描述 |
|------|------|------|
| `/cua/screenshot` | POST | 屏幕截图 |
| `/cua/screen/info` | GET | 获取屏幕信息 |
| `/cua/mouse/click` | POST | 鼠标点击 |
| `/cua/mouse/move` | POST | 鼠标移动 |
| `/cua/mouse/drag` | POST | 鼠标拖拽 |
| `/cua/mouse/scroll` | POST | 鼠标滚动 |
| `/cua/mouse/position` | GET | 获取鼠标位置 |
| `/cua/keyboard/type` | POST | 键盘输入 |
| `/cua/keyboard/press` | POST | 按键 |
| `/cua/keyboard/hotkey` | POST | 组合键 |
| `/cua/window/list` | GET | 窗口列表 |
| `/cua/window/active` | GET | 活动窗口 |
| `/cua/window/activate` | POST | 激活窗口 |
| `/cua/window/minimize` | POST | 最小化窗口 |
| `/cua/window/maximize` | POST | 最大化窗口 |
| `/cua/window/close` | POST | 关闭窗口 |
| `/cua/window/move` | POST | 移动窗口 |
| `/cua/window/resize` | POST | 调整窗口大小 |
| `/cua/ocr` | POST | OCR 识别 |
| `/cua/ocr/find-text` | POST | 查找文本 |
| `/cua/record/action` | POST | 录制控制 |
| `/cua/record/actions` | GET | 获取录制操作 |
| `/cua/record/play` | POST | 回放操作 |
| `/cua/safety/status` | GET | 安全状态 |
| `/cua/safety/permission` | POST | 设置权限 |
| `/cua/safety/logs` | GET | 审计日志 |

### 3.2 MCP API 端点

| 端点 | 方法 | 描述 |
|------|------|------|
| `/mcp/tools` | GET | 列出所有工具 |
| `/mcp/call` | POST | 调用工具 |
| `/mcp/servers` | GET | 列出服务器 |
| `/mcp/servers` | POST | 添加服务器 |
| `/mcp/servers/{name}` | DELETE | 删除服务器 |
| `/mcp/servers/{name}/status` | GET | 服务器状态 |
| `/mcp/servers/{name}/reconnect` | POST | 重连服务器 |
| `/mcp/servers/{name}/tools` | GET | 服务器工具 |
| `/mcp/status` | GET | 整体状态 |

## 4. 数据流转机制

### 4.1 CUA 数据流

```
前端请求 → FastAPI 路由 → CUA 控制器 → 底层操作 (pyautogui/mss/pytesseract)
    ↓
返回结果 → OperationResult/ScreenshotResult → JSON 响应
```

### 4.2 MCP 数据流

```
前端请求 → FastAPI 路由 → MCPServerManager → MCPClient → JSON-RPC 2.0
    ↓
外部 MCP 服务器 → 工具执行 → MCPToolResult → JSON 响应
```

### 4.3 Skill 集成数据流

```
CUA Skill → SkillRegistry → SkillExecutor → CUA 模块
    ↓
MemoryAwareSkill → OperationMemoryManager → 记录操作历史
```

## 5. 模块交互关系

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend (React)                          │
├─────────────────────────────────────────────────────────────────┤
│  CUAControl.tsx  │  ActionRecorder.tsx  │  SkillMemory.tsx  │ MCPTools.tsx  │
└────────┬─────────┴──────────┬───────────┴────────┬────────┴───────┬───────┘
         │                    │                    │                │
         ▼                    ▼                    ▼                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Backend (FastAPI)                            │
├─────────────────────────────────────────────────────────────────┤
│  api/cua.py      │  api/mcp.py           │  skills/             │
└────────┬─────────┴──────────┬───────────┴────────┬───────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐
│   CUA Module    │  │   MCP Module    │  │   Skills Module     │
│  (pyautogui)    │  │  (JSON-RPC)     │  │   (CUA Skills)      │
└─────────────────┘  └─────────────────┘  └─────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐
│  Desktop OS     │  │  External MCP   │  │  OperationMemory    │
│  (Windows/Mac)  │  │  Servers        │  │  (Learning)         │
└─────────────────┘  └─────────────────┘  └─────────────────────┘
```

## 6. 安全机制

### 6.1 CUA 安全控制

- **权限级别**: READ_ONLY, INTERACTIVE, FULL_CONTROL
- **敏感操作检测**: 危险命令、系统操作
- **FAILSAFE 机制**: 鼠标移至屏幕角落自动停止
- **审计日志**: 所有操作记录

### 6.2 MCP 安全控制

- **服务器白名单**: 可配置允许的服务器
- **工具权限**: 按工具控制访问权限
- **调用限制**: 防止滥用

## 7. 前端路由配置

```typescript
// App.tsx
const routes = [
  // ... 其他路由
  { path: '/cua-control', element: <CUAControl /> },
  { path: '/cua-recorder', element: <ActionRecorder /> },
  { path: '/cua-memory', element: <SkillMemory /> },
  { path: '/mcp', element: <MCPTools /> },
]
```

## 8. 后端路由注册

```python
# main.py
from api import cua, mcp

app.include_router(cua, tags=["CUA - Computer Use Agent"])
app.include_router(mcp, tags=["MCP"])
```

## 9. Skill 注册

```python
# skills/implemented/cua_skills.py
CUA_SKILLS = [
    ScreenshotSkill,
    MouseClickSkill,
    MouseMoveSkill,
    KeyboardTypeSkill,
    WindowListSkill,
    AppLaunchSkill,
    FindTextSkill,
]
```

## 10. 依赖关系

### 10.1 Python 依赖

```txt
# CUA 依赖
pyautogui>=0.9.54
mss>=9.0.0
pytesseract>=0.3.10
Pillow>=9.0.0
pywin32>=305  # Windows only

# MCP 依赖
websockets>=11.0
httpx>=0.24.0
```

### 10.2 系统依赖

- **Tesseract OCR**: 文本识别
- **Windows API**: 窗口管理 (Windows)

## 11. 配置项

```bash
# .env
CUA_PERMISSION_LEVEL=interactive
CUA_FAILSAFE_ENABLED=true
CUA_AUDIT_ENABLED=true
MCP_MAX_SERVERS=10
MCP_CONNECTION_TIMEOUT=30
```

## 12. 错误处理

### 12.1 CUA 异常

| 异常 | HTTP 状态码 | 描述 |
|------|-------------|------|
| CUAError | 500 | 通用 CUA 错误 |
| PermissionDeniedError | 403 | 权限不足 |
| WindowNotFoundError | 404 | 窗口未找到 |
| OCRError | 400 | OCR 识别失败 |
| TesseractNotInstalledError | 503 | Tesseract 未安装 |

### 12.2 MCP 异常

| 异常 | HTTP 状态码 | 描述 |
|------|-------------|------|
| MCPConnectionError | 503 | 连接失败 |
| MCPToolNotFoundError | 404 | 工具未找到 |
| MCPTimeoutError | 504 | 超时 |

## 13. 性能优化

### 13.1 CUA 优化

- 截图缓存：避免重复截图
- 异步操作：所有操作支持 async
- 批量操作：支持批量执行

### 13.2 MCP 优化

- 工具缓存：MCPToolRegistry 缓存
- 连接池：复用 MCP 连接
- 超时控制：可配置超时时间

## 14. 测试覆盖

- `tests/test_cua.py`: CUA 模块测试
- `tests/test_mcp.py`: MCP 模块测试
- `tests/test_skills_registry.py`: Skill 集成测试

## 15. 版本兼容性

| 模块 | 最低版本 | 推荐版本 |
|------|----------|----------|
| Python | 3.10 | 3.11+ |
| FastAPI | 0.100 | 0.109+ |
| Pydantic | 2.0 | 2.5+ |
| React | 18.0 | 18.2+ |
