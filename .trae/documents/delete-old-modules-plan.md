# 删除旧模块计划 - 完全切换到新模块

## 一、概述

将旧的分散模块完全删除，统一使用重构后的新模块架构。

### 新旧模块对照表

| 功能 | 旧模块 | 新模块 | API路径变化 |
|-----|-------|-------|------------|
| 对话历史 | `chat_history.py` | `chat/` | `/chat` → `/v2/chat` |
| 对话上下文 | `dialog_context.py` | `chat/context.py` | `/dialog-context` → `/v2/chat/{id}/context` |
| 会话管理 | `session.py` | `chat/session.py` | `/sessions` → `/v2/chat` |
| 记忆 | `memory.py`, `enhanced_memory.py` | `memory_new/` | `/memory`, `/memory/v2` → `/v2/memory` |
| 知识库/RAG | `rag.py`, `knowledge_base.py` | `knowledge/` | `/rag`, `/knowledge-base` → `/v2/knowledge` |
| 推理 | `inference.py` | `inference/` | `/inference` → `/inference` (保持不变) |

## 二、待删除文件列表

### 后端文件 (8个)

```
server/api/
├── chat_history.py        # 删除
├── dialog_context.py      # 删除
├── session.py             # 删除
├── memory.py              # 删除
├── enhanced_memory.py     # 删除
├── rag.py                 # 删除
├── knowledge_base.py      # 删除
└── inference.py           # 删除 (已有 inference/ 目录)
```

### 备份文件 (可选删除)

```
server/api/
├── inference.py.bak       # 删除
└── inference_fix.py       # 删除
```

## 三、待修改文件

### 后端文件

#### 1. `server/main.py`

**修改内容：**
- 移除旧模块导入
- 移除旧路由注册
- 更新 lifespan 中的初始化逻辑

**删除的导入：**
```python
# 删除
from api import chat_history, rag, memory, dialog_context
from api import enhanced_memory
from api import session as session_api
```

**删除的路由注册：**
```python
# 删除
app.include_router(chat_history, prefix="/chat", tags=["对话历史"])
app.include_router(rag, prefix="/rag", tags=["RAG 知识库"])
app.include_router(memory, prefix="/memory", tags=["智能记忆"])
app.include_router(enhanced_memory.router, prefix="/memory/v2", tags=["增强记忆系统"])
app.include_router(dialog_context, prefix="/dialog-context", tags=["对话上下文管理"])
app.include_router(session_api, prefix="/sessions", tags=["会话管理"])
```

**更新的 lifespan 初始化：**
```python
# 将
from api.chat_history import init_chat_db
init_chat_db()

# 改为
from api.chat.session import SessionStore
SessionStore()  # 自动初始化
```

#### 2. `server/api/__init__.py`

**修改内容：**
- 移除旧模块导出
- 保留设备、模型、数据集、训练等核心模块

**删除的导出：**
```python
# 删除
from api.inference import router as inference_router
from api.chat_history import router as chat_history
from api.rag import router as rag
from api.memory import router as memory
from api.dialog_context import router as dialog_context
from api.session import router as session
from api.knowledge_base import router as knowledge_base

# 兼容性别名
inference = inference_router
```

### 前端文件

#### 1. `client/src/pages/Chat.tsx`

**修改内容：**
- `/rag/collections` → `/v2/knowledge/collections`
- `/rag/query` → `/v2/knowledge/search`

#### 2. `client/src/pages/KnowledgeBase.tsx`

**修改内容：**
- `/rag/upload` → `/v2/knowledge/upload`
- `/rag/collection/{id}` → `/v2/knowledge/collections/{id}`
- `/rag/collection/{id}/document/{docId}` → `/v2/knowledge/collections/{id}/documents/{docId}`

#### 3. `client/src/services/memoryApi.ts`

**修改内容：**
- `API_BASE = 'http://127.0.0.1:8000/memory/v2'` → `API_BASE = 'http://127.0.0.1:8000/v2/memory'`
- `/sessions` 路由需要适配新的 API 结构

#### 4. `client/vite.config.ts`

**修改内容：**
- `/rag` 代理 → `/v2/knowledge`

## 四、实施步骤

### 阶段1：备份与准备
1. 创建备份目录
2. 备份待删除的文件

### 阶段2：后端修改
1. 修改 `server/api/__init__.py`
2. 修改 `server/main.py`
3. 删除旧模块文件
4. 删除备份文件

### 阶段3：前端修改
1. 修改 `client/src/pages/Chat.tsx`
2. 修改 `client/src/pages/KnowledgeBase.tsx`
3. 修改 `client/src/services/memoryApi.ts`
4. 修改 `client/vite.config.ts`

### 阶段4：验证
1. 启动后端服务，验证所有 API 端点正常
2. 启动前端服务，验证页面功能正常
3. 运行测试脚本确认无错误

## 五、风险评估

| 风险 | 影响 | 缓解措施 |
|-----|------|---------|
| 前端API路径不兼容 | 页面功能失效 | 同步更新前端代码 |
| 数据库结构变化 | 历史数据丢失 | 新模块使用相同数据库结构 |
| 第三方依赖旧模块 | 功能异常 | 检查所有依赖引用 |

## 六、回滚方案

如果切换失败，可以从备份目录恢复删除的文件，并恢复 main.py 和 __init__.py 的修改。
