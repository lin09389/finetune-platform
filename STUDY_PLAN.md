# 🎓 优秀项目系统化学习计划

## 📅 学习时间表（7 天）

| 天数 | 主题 | 目标 | 产出 |
|------|------|------|------|
| **第 1 天** | AnythingLLM 架构分析 | 理解 RAG 全流程 | 架构图 + 核心流程文档 |
| **第 2 天** | AnythingLLM 代码实战 | 掌握文档处理 | 文档解析模块代码 |
| **第 3 天** | Open WebUI 界面分析 | 学习聊天 UI 设计 | UI 组件优化方案 |
| **第 4 天** | Open WebUI 流式输出 | 掌握 SSE 流式传输 | 流式 API 优化 |
| **第 5 天** | Flowise 工作流架构 | 理解可视化编排 | 工作流设计方案 |
| **第 6 天** | LocalAI 模型管理 | 学习模型管理 | 模型下载管理器 |
| **第 7 天** | 整合实践 | 应用到本项目 | 新功能实现 |

---

## 📚 第 1-2 天：AnythingLLM 深度学习

### 学习目标
1. 理解 RAG（检索增强生成）完整流程
2. 掌握文档处理技术
3. 学习向量数据库集成

### 核心架构
```
┌─────────────────────────────────────────────────────────┐
│                    AnythingLLM                          │
├─────────────────────────────────────────────────────────┤
│  Frontend (React)                                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │  Workspace   │  │    Chat      │  │  Documents   │ │
│  │  Selector    │  │   Interface  │  │   Manager    │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
├─────────────────────────────────────────────────────────┤
│  Backend (Node.js + Express)                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │  Document    │  │    Chat      │  │   Vector     │ │
│  │  Controller  │  │  Controller  │  │   Controller │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
├─────────────────────────────────────────────────────────┤
│  Data Layer                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │   SQLite     │  │   LanceDB    │  │   Files      │ │
│  │  (Metadata)  │  │  (Vectors)   │  │  (Documents) │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### RAG 核心流程
```
1. 文档上传 → 2. 文本提取 → 3. 分块 → 4. 向量化 → 5. 存储
                                              ↓
6. 用户提问 → 7. 问题向量化 → 8. 相似度检索 → 9. 组装上下文 → 10. LLM 生成
```

### 关键技术点

#### 1. 文档解析
```javascript
// 支持多种格式
- PDF → pdf-parse
- DOCX → mammoth
- TXT → fs.readFile
- Markdown → fs.readFile
```

#### 2. 文本分块策略
```javascript
// 按字符数分块（重叠避免语义断裂）
chunkSize: 500
chunkOverlap: 50

// 按语义分块（更智能）
- 按段落
- 按标题
- 按句子边界
```

#### 3. 向量化
```python
# 使用 sentence-transformers
from sentence_transformers import SentenceTransformer
model = SentenceTransformer('all-MiniLM-L6-v2')
embeddings = model.encode(chunks)
```

#### 4. 向量存储
```python
# ChromaDB 示例
import chromadb
client = chromadb.Client()
collection = client.create_collection("documents")
collection.add(
    embeddings=[...],
    documents=[...],
    ids=[...]
)
```

#### 5. 相似度检索
```python
# 余弦相似度搜索
results = collection.query(
    query_embeddings=[query_embedding],
    n_results=5,
    include=["documents", "distances"]
)
```

---

## 📚 第 3-4 天：Open WebUI 深度学习

### 学习目标
1. 掌握现代化聊天界面设计
2. 学习 SSE 流式输出实现
3. 理解对话状态管理

### 核心架构
```
┌─────────────────────────────────────────────────────────┐
│                     Open WebUI                          │
├─────────────────────────────────────────────────────────┤
│  Frontend (SvelteKit)                                   │
│  ┌────────────────────────────────────────────────────┐ │
│  │  Chat.svelte                                       │ │
│  │  ├─ MessageList.svelte                             │ │
│  │  ├─ MessageInput.svelte                            │ │
│  │  ├─ Sidebar.svelte (历史对话)                       │ │
│  │  └─ ModelSelector.svelte                           │ │
│  └────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────┤
│  Backend (FastAPI)                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │   chat.py    │  │    rag.py    │  │   models.py  │ │
│  │  (聊天 API)  │  │  (RAG API)   │  │  (模型 API)  │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### 流式输出实现

#### 后端（FastAPI）
```python
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse

async def generate_stream(prompt: str):
    async def event_generator():
        for chunk in llm.generate_stream(prompt):
            yield {
                "event": "message",
                "data": json.dumps({"content": chunk})
            }
    
    return EventSourceResponse(event_generator())
```

#### 前端（Svelte）
```svelte
<script>
  async function streamResponse() {
    const response = await fetch('/api/chat/stream', {
      method: 'POST',
      body: JSON.stringify({ messages })
    });
    
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      
      const text = decoder.decode(value);
      // 解析 SSE 数据
      const lines = text.split('\n');
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = JSON.parse(line.slice(6));
          setContent(prev => prev + data.content);
        }
      }
    }
  }
</script>
```

### 聊天界面最佳实践

#### 1. 消息组件结构
```tsx
<MessageList>
  <Message role="user">
    <Avatar />
    <Bubble>
      <Content markdown />
      <Actions copy retry delete />
    </Bubble>
  </Message>
  
  <Message role="assistant">
    <Avatar />
    <Bubble>
      <Content markdown codeHighlight />
      <Actions copy retry delete />
    </Bubble>
  </Message>
</MessageList>
```

#### 2. 自动滚动
```tsx
const messagesEndRef = useRef(null);

const scrollToBottom = () => {
  messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
};

useEffect(() => {
  scrollToBottom();
}, [messages]);
```

#### 3. 输入优化
```tsx
<TextArea
  value={input}
  onChange={handleChange}
  onPressEnter={(e) => {
    if (!e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }}
  placeholder="输入消息... (Shift+Enter 换行)"
/>
```

---

## 📚 第 5 天：Flowise 工作流架构

### 学习目标
1. 理解可视化节点系统
2. 学习有向图执行引擎
3. 掌握 React Flow 集成

### 核心架构
```
┌─────────────────────────────────────────────────────────┐
│                       Flowise                           │
├─────────────────────────────────────────────────────────┤
│  Frontend (React Flow)                                  │
│  ┌────────────────────────────────────────────────────┐ │
│  │  Canvas                                            │ │
│  │  ├─ Input Node    → 用户输入                        │ │
│  │  ├─ LLM Node      → 模型调用                        │ │
│  │  ├─ RAG Node      → 向量检索                        │ │
│  │  ├─ Output Node   → 结果输出                        │ │
│  │  └─ Edges         → 数据流连接                      │ │
│  └────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────┤
│  Backend (Execution Engine)                             │
│  ┌────────────────────────────────────────────────────┐ │
│  │  Graph Executor                                    │ │
│  │  1. 拓扑排序确定执行顺序                            │ │
│  │  2. 节点依次执行                                    │ │
│  │  3. 边传递数据                                      │ │
│  └────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### 节点系统设计

#### 1. 节点接口
```typescript
interface Node {
  id: string;
  type: 'input' | 'llm' | 'rag' | 'output';
  position: { x: number; y: number };
  data: {
    label: string;
    config: Record<string, any>;
  };
}

interface Edge {
  id: string;
  source: string;  // 源节点 ID
  target: string;  // 目标节点 ID
  data?: any;      // 传递的数据
}
```

#### 2. 执行引擎
```python
class WorkflowExecutor:
    def __init__(self, nodes: List[Node], edges: List[Edge]):
        self.graph = self.build_graph(nodes, edges)
    
    def build_graph(self, nodes, edges):
        """构建有向图"""
        graph = {node.id: [] for node in nodes}
        for edge in edges:
            graph[edge.source].append(edge.target)
        return graph
    
    def execute(self, input_data):
        """执行工作流"""
        # 拓扑排序
        order = self.topological_sort()
        
        # 依次执行节点
        results = {}
        for node_id in order:
            node = self.get_node(node_id)
            results[node_id] = node.execute(results)
        
        return results
```

#### 3. React Flow 集成
```tsx
import ReactFlow, { Background, Controls } from 'reactflow';
import 'reactflow/dist/style.css';

function WorkflowCanvas() {
  const [nodes, setNodes] = useState([]);
  const [edges, setEdges] = useState([]);

  return (
    <div style={{ height: 600 }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={setNodes}
        onEdgesChange={setEdges}
        fitView
      >
        <Background />
        <Controls />
      </ReactFlow>
    </div>
  );
}
```

---

## 📚 第 6 天：LocalAI 模型管理

### 学习目标
1. 学习 HuggingFace 集成
2. 掌握模型下载管理
3. 理解模型加载优化

### 核心功能

#### 1. 模型浏览
```python
from huggingface_hub import HfApi

api = HfApi()

# 搜索模型
models = api.list_models(
    search="llama",
    filter="text-generation",
    sort="downloads",
    direction=-1
)

# 获取模型信息
model_info = api.model_info("meta-llama/Llama-2-7b")
```

#### 2. 下载管理
```python
from huggingface_hub import snapshot_download
from tqdm import tqdm

class DownloadManager:
    def download(self, repo_id, local_dir):
        # 获取文件列表
        files = api.list_repo_files(repo_id)
        
        # 显示进度
        with tqdm(total=len(files)) as pbar:
            for file in files:
                self.download_file(repo_id, file, local_dir)
                pbar.update(1)
    
    def download_file(self, repo_id, filename, local_dir):
        # 支持断点续传
        hf_hub_download(
            repo_id=repo_id,
            filename=filename,
            local_dir=local_dir,
            resume_download=True
        )
```

#### 3. 模型加载优化
```python
import torch
from transformers import AutoModelForCausalLM

class ModelLoader:
    def load(self, model_path, use_gpu=True):
        # 自动检测 GPU
        if use_gpu and torch.cuda.is_available():
            device = "cuda"
            dtype = torch.float16
        else:
            device = "cpu"
            dtype = torch.float32
        
        # 智能内存管理
        model = AutoModelForCausalLM.from_pretrained(
            model_path,
            device_map="auto",
            torch_dtype=dtype,
            low_cpu_mem_usage=True,
        )
        
        return model
```

---

## 📚 第 7 天：整合实践

### 应用到 finetune-platform

#### 1. RAG 知识库（学习 AnythingLLM）
```
server/
├── api/
│   └── rag.py          # 新建
├── rag/
│   ├── document_parser.py
│   ├── text_chunker.py
│   ├── embedder.py
│   └── vector_store.py
└── data/
    └── vectors/        # 向量数据库存储
```

#### 2. 聊天界面优化（学习 Open WebUI）
```tsx
// 添加功能
- 消息搜索
- 对话导出
- 快捷键支持
- 更好的 Markdown 渲染
```

#### 3. 模型下载管理（学习 LocalAI）
```python
# server/api/model_hub.py
- 浏览 HuggingFace
- 下载进度显示
- 断点续传
- 模型推荐列表
```

#### 4. 可视化工作流（学习 Flowise，可选）
```tsx
// client/src/pages/Workflow.tsx
- React Flow 画布
- 节点拖拽
- 连接管理
```

---

## ✅ 每日检查清单

### 第 1 天
- [ ] 浏览 AnythingLLM GitHub 仓库
- [ ] 阅读文档处理相关代码
- [ ] 画出 RAG 流程图
- [ ] 记录可借鉴的设计

### 第 2 天
- [ ] 实现文档解析模块
- [ ] 集成向量数据库
- [ ] 测试完整的 RAG 流程

### 第 3 天
- [ ] 分析 Open WebUI 聊天界面
- [ ] 优化 ChatMessage 组件
- [ ] 添加更多消息操作

### 第 4 天
- [ ] 实现 SSE 流式输出
- [ ] 优化前端流式接收
- [ ] 添加打字机效果

### 第 5 天
- [ ] 学习 React Flow 基础
- [ ] 设计节点系统
- [ ] 实现简单的工作流执行器

### 第 6 天
- [ ] 集成 HuggingFace API
- [ ] 实现模型下载管理
- [ ] 添加下载进度显示

### 第 7 天
- [ ] 选择 1-2 个功能实现
- [ ] 整合到 finetune-platform
- [ ] 编写文档

---

## 📖 参考资源

### GitHub 链接
- AnythingLLM: https://github.com/mintplex-labs/anything-llm
- Open WebUI: https://github.com/open-webui/open-webui
- Flowise: https://github.com/FlowiseAI/Flowise
- LocalAI: https://github.com/localai/localai

### 技术文档
- HuggingFace Hub: https://huggingface.co/docs/hub
- ChromaDB: https://docs.trychroma.com/
- React Flow: https://reactflow.dev/docs
- FastAPI Streaming: https://fastapi.tiangolo.com/advanced/event-streams

---

**开始学习吧！需要我帮你深入分析哪个项目？** 🚀
