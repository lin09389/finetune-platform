# LocalAI Studio 改进计划

基于 CLAUDE.md 开发指南制定的详细改进计划

---

## 一、现状分析

### 1.1 现有功能 ✅

| 模块 | 状态 | 说明 |
|------|------|------|
| 后端 API | ✅ 完整 | FastAPI + 推理/训练/模型管理 |
| 前端页面 | ✅ 完整 | React + Ant Design |
| Electron 集成 | ✅ 基础 | 主进程/预加载脚本 |
| 状态管理 | ✅ 完整 | Zustand + 持久化 |
| Ollama 集成 | ✅ 完整 | 流式推理/聊天 API |
| 设备信息 | ✅ 完整 | GPU/显存检测 |

### 1.2 缺失功能 ❌

| 功能 | 优先级 | 说明 |
|------|--------|------|
| llama.cpp 集成 | P0 | 核心推理引擎缺失 |
| 专用 Chat 页面 | P0 | 当前只有 Inference 测试页 |
| 对话历史管理 | P0 | 无本地存储/加载 |
| 模型下载管理 | P1 | 无 HuggingFace 集成 |
| RAG 知识库 | P2 | 文档/向量检索缺失 |
| 可视化工作流 | P2 | Agent 编排缺失 |

### 1.3 技术问题 ⚠️

```
1. 推理引擎依赖 Ollama，缺少原生 llama.cpp 支持
2. 前端 Inference 页面偏测试向，非聊天体验
3. 对话历史无存储，刷新即丢失
4. Electron 未打包验证
```

---

## 二、P0 - MVP 核心（第 1 周）

### 2.1 聊天界面改造

**目标**: 将 Inference 页面改造成专业 Chat 界面

**任务**:
- [ ] 新建 `Chat.tsx` 页面，替代 Inference.tsx
- [ ] 气泡式对话 UI（用户/助手区分）
- [ ] 流式输出动画优化
- [ ] 支持 Markdown 渲染（react-markdown）
- [ ] 支持代码高亮（highlight.js）
- [ ] 复制/重新生成/删除消息

**文件**:
```
client/src/pages/Chat.tsx (新建)
client/src/components/ChatMessage.tsx (新建)
```

**预计工时**: 2 晚

---

### 2.2 多模型切换增强

**目标**: 支持加载和切换不同模型

**任务**:
- [ ] 模型列表下拉选择（带预览）
- [ ] 显示模型信息（参数量/类型）
- [ ] 快速切换（无需刷新）
- [ ] 模型加载状态指示

**API 扩展**:
```python
# server/api/inference.py
@router.get("/models/available")
async def get_available_models():
    """获取可用模型列表（含 llama.cpp 格式）"""
```

**预计工时**: 1 晚

---

### 2.3 对话历史管理

**目标**: 本地存储对话记录

**任务**:
- [ ] 数据库设计（SQLite/IndexedDB）
- [ ] 对话 CRUD API
- [ ] 历史列表侧边栏
- [ ] 搜索/过滤功能
- [ ] 导出/导入对话

**文件**:
```
server/api/chat_history.py (新建)
client/src/pages/History.tsx (改造)
```

**数据库设计**:
```sql
CREATE TABLE chat_sessions (
    id TEXT PRIMARY KEY,
    title TEXT,
    model_id TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE TABLE chat_messages (
    id TEXT PRIMARY KEY,
    session_id TEXT,
    role TEXT,
    content TEXT,
    created_at TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES chat_sessions(id)
);
```

**预计工时**: 2 晚

---

### 2.4 llama.cpp 集成（核心）

**目标**: 原生支持 llama.cpp 推理引擎

**任务**:
- [ ] 后端集成 llama-cpp-python
- [ ] GGUF 模型加载
- [ ] 流式生成 API
- [ ] 显存优化配置

**文件**:
```
server/backends/llama_cpp_backend.py (新建)
server/requirements.txt (添加 llama-cpp-python)
```

**依赖**:
```bash
pip install llama-cpp-python
```

**API 扩展**:
```python
@router.post("/inference/llama")
async def llama_inference(request: LlamaRequest):
    """llama.cpp 原生推理"""
```

**预计工时**: 3 晚

---

## 三、P1 - 增强功能（第 2 周）

### 3.1 模型下载管理

**目标**: 集成 HuggingFace，支持模型浏览和下载

**任务**:
- [ ] HuggingFace API 集成
- [ ] 模型搜索/过滤
- [ ] 下载进度显示
- [ ] 断点续传
- [ ] 模型推荐列表

**文件**:
```
server/api/model_hub.py (新建)
client/src/pages/ModelHub.tsx (新建)
```

**预计工时**: 2 晚

---

### 3.2 API 服务

**目标**: 提供 RESTful API 供外部调用

**任务**:
- [ ] OpenAI 兼容 API 格式
- [ ] API Key 认证
- [ ] 速率限制
- [ ] API 文档（Swagger）

**API 端点**:
```
POST /v1/chat/completions
POST /v1/completions
GET  /v1/models
```

**预计工时**: 2 晚

---

## 四、P2 - 高级功能（第 3-4 周）

### 4.1 RAG 知识库

**目标**: 文档上传、向量检索

**任务**:
- [ ] 文档上传（PDF/TXT/MD）
- [ ] 文本分块
- [ ] 向量嵌入（sentence-transformers）
- [ ] 向量数据库（Chroma/FAISS）
- [ ] 检索增强生成

**文件**:
```
server/rag/ (新建目录)
server/api/knowledge_base.py (新建)
```

**预计工时**: 4 晚

---

### 4.2 可视化工作流

**目标**: 拖拽式 Agent 编排

**任务**:
- [ ] 流程图编辑器（React Flow）
- [ ] 节点类型（输入/LLM/输出）
- [ ] 连接管理
- [ ] 工作流执行引擎

**预计工时**: 5 晚

---

## 五、开发时间表

| 周次 | 阶段 | 任务 | 工时 |
|------|------|------|------|
| 第 1 周 | P0 | Chat 界面 + 对话历史 + llama.cpp | 8 晚 |
| 第 2 周 | P1 | 模型下载 + API 服务 | 4 晚 |
| 第 3 周 | P2 | RAG 知识库 | 4 晚 |
| 第 4 周 | P2 | 可视化工作流 | 5 晚 |

---

## 六、立即行动项（本周）

### 第 1 晚：Chat 界面基础
- [ ] 创建 `Chat.tsx` 基础结构
- [ ] 实现消息列表渲染
- [ ] 接入流式 API

### 第 2 晚：Chat 界面增强
- [ ] Markdown 渲染
- [ ] 代码高亮
- [ ] 消息操作按钮

### 第 3 晚：对话历史
- [ ] 设计数据库 Schema
- [ ] 实现 CRUD API
- [ ] 历史列表 UI

### 第 4-5 晚：llama.cpp 集成
- [ ] 安装依赖
- [ ] 实现后端
- [ ] 前端联调

---

## 七、技术栈确认

| 组件 | 技术选型 | 说明 |
|------|----------|------|
| 推理引擎 | llama.cpp + Ollama | 双引擎支持 |
| 向量数据库 | Chroma | 轻量/易集成 |
| Markdown | react-markdown + remark-gfm | 完整 Markdown 支持 |
| 代码高亮 | highlight.js | 多语言支持 |
| 流程图 | React Flow | 拖拽式编辑 |

---

## 八、风险与应对

| 风险 | 影响 | 应对 |
|------|------|------|
| llama.cpp 编译问题 | 高 | 预编译 wheel/使用 Ollama 降级 |
| 显存不足 | 中 | 量化模型/CPU 推理 |
| Electron 打包体积大 | 中 | 排除不必要依赖 |
| 开发时间不足 | 中 | 优先 P0，P1/P2 延后 |

---

**制定日期**: 2026-03-05  
**版本**: v1.0  
**状态**: 待执行
