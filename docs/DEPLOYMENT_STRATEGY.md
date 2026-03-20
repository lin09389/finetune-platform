# 模块部署策略与版本控制

## 1. 部署架构

### 1.1 生产环境部署

```
┌─────────────────────────────────────────────────────────────────┐
│                        Docker Compose                            │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │   Frontend  │  │   Backend   │  │      Ollama (可选)       │  │
│  │   (Nginx)   │  │  (FastAPI)  │  │     (推理后端)           │  │
│  │   :80/443   │  │    :8000    │  │        :11434           │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
│                          │                                       │
│                          ▼                                       │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                    数据持久化层                              ││
│  │  ┌───────────┐  ┌───────────┐  ┌───────────────────────┐   ││
│  │  │  models/  │  │ datasets/ │  │   ChromaDB (向量存储)  │   ││
│  │  └───────────┘  └───────────┘  └───────────────────────┘   ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 开发环境部署

```bash
# 后端开发服务器
cd server
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload

# 前端开发服务器
cd client
npm run dev
```

## 2. 新模块部署步骤

### 2.1 CUA 模块部署

#### 系统依赖

```bash
# Windows
# 无需额外安装，pywin32 会自动处理

# macOS
brew install tesseract

# Linux
sudo apt-get install tesseract-ocr
sudo apt-get install python3-tk
```

#### Python 依赖

```bash
pip install pyautogui>=0.9.54
pip install pytesseract>=0.3.10
pip install Pillow>=9.0.0
pip install mss>=9.0.0
```

#### 配置项

```bash
# .env
CUA_PERMISSION_LEVEL=interactive
CUA_FAILSAFE_ENABLED=true
CUA_AUDIT_ENABLED=true
```

### 2.2 MCP 模块部署

#### Python 依赖

```bash
pip install websockets>=11.0
```

#### 配置项

```bash
# .env
MCP_MAX_SERVERS=10
MCP_CONNECTION_TIMEOUT=30
```

## 3. 版本控制策略

### 3.1 分支策略

```
main (生产分支)
  │
  ├── develop (开发分支)
  │     │
  │     ├── feature/cua-module (CUA 功能开发)
  │     ├── feature/mcp-module (MCP 功能开发)
  │     └── feature/skill-memory (记忆集成)
  │
  └── release/v2.1.0 (发布分支)
```

### 3.2 版本号规范

- **主版本号**: 重大架构变更
- **次版本号**: 新功能模块
- **修订号**: Bug 修复和小改进

示例：
- `2.0.0` - 初始版本
- `2.1.0` - 添加 CUA/MCP 模块
- `2.1.1` - 修复 CUA 安全问题

### 3.3 变更日志

```markdown
## [2.1.0] - 2025-03-16

### Added
- CUA (Computer Use Agent) 模块
  - 屏幕截图与 OCR
  - 鼠标/键盘控制
  - 窗口管理
  - 操作录制与回放
  - 安全控制与审计

- MCP (Model Context Protocol) 模块
  - JSON-RPC 2.0 协议支持
  - 外部工具集成
  - 工具到 Skill 转换

- 记忆-技能集成
  - 操作记忆管理
  - 用户偏好学习
  - 上下文注入

### Changed
- 更新 requirements.txt 添加新依赖
- 前端添加新页面路由

### Fixed
- TypeScript 类型错误修复
- 测试用例更新
```

## 4. 回滚预案

### 4.1 快速回滚

```bash
# 回滚到上一个版本
git checkout HEAD~1 -- server/cua server/mcp server/skills
git checkout HEAD~1 -- client/src/pages/CUAControl.tsx
git checkout HEAD~1 -- client/src/pages/MCPTools.tsx
git checkout HEAD~1 -- client/src/pages/ActionRecorder.tsx
git checkout HEAD~1 -- client/src/pages/SkillMemory.tsx

# 重启服务
docker compose restart api
```

### 4.2 数据库回滚

```bash
# ChromaDB 数据备份
cp -r data/chroma data/chroma_backup_$(date +%Y%m%d)

# 恢复
cp -r data/chroma_backup_YYYYMMDD data/chroma
```

### 4.3 配置回滚

```bash
# 恢复环境变量
cp .env.backup .env

# 重启服务
docker compose down
docker compose up -d
```

## 5. 监控与告警

### 5.1 健康检查端点

```bash
# 后端健康检查
curl http://localhost:8000/health

# CUA 模块状态
curl http://localhost:8000/cua/safety/status

# MCP 模块状态
curl http://localhost:8000/mcp/status
```

### 5.2 日志监控

```bash
# 查看后端日志
docker compose logs -f api

# 筛选 CUA 相关日志
docker compose logs -f api | grep -i cua

# 筛选 MCP 相关日志
docker compose logs -f api | grep -i mcp
```

### 5.3 性能指标

- CUA 操作响应时间 < 100ms
- MCP 工具调用超时 < 30s
- 内存使用 < 500MB (空闲状态)

## 6. 安全加固

### 6.1 CUA 安全配置

```bash
# 生产环境推荐配置
CUA_PERMISSION_LEVEL=read_only
CUA_AUDIT_ENABLED=true
CUA_AUDIT_LOG_PATH=/var/log/cua/audit.log
```

### 6.2 MCP 安全配置

```bash
# 服务器白名单
MCP_ALLOWED_SERVERS=filesystem,github,slack

# 工具权限控制
MCP_TOOL_PERMISSIONS=filesystem:read,github:read
```

## 7. 部署检查清单

- [ ] Python 依赖已安装
- [ ] 环境变量已配置
- [ ] 数据库迁移已完成
- [ ] 前端构建成功
- [ ] 后端启动成功
- [ ] 健康检查通过
- [ ] CUA 安全配置已启用
- [ ] MCP 服务器已配置
- [ ] 日志输出正常
- [ ] 监控告警已配置
