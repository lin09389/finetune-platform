# 🏆 本地 AI 推理平台 - 优秀实践指南

## 📚 来自顶级项目的最佳实践

综合 AnythingLLM、Open WebUI、Flowise、LM Studio 等项目的成功经验

---

## 🎯 一、产品架构最佳实践

### 1.1 分层架构（推荐）

```
┌─────────────────────────────────────┐
│         前端层 (Electron + React)    │
│  - UI 组件                            │
│  - 状态管理 (Zustand)                │
│  - 本地存储 (IndexedDB)              │
└─────────────────┬───────────────────┘
                  │ IPC
┌─────────────────▼───────────────────┐
│         后端层 (FastAPI)             │
│  - API 路由                          │
│  - 业务逻辑                          │
│  - 模型管理                          │
└─────────────────┬───────────────────┘
                  │
┌─────────────────▼───────────────────┐
│         推理层 (llama.cpp)           │
│  - 模型加载                          │
│  - 推理执行                          │
│  - 流式输出                          │
└─────────────────────────────────────┘
```

**为什么这样设计**：
- ✅ 职责清晰，易于维护
- ✅ 各层可独立测试
- ✅ 方便替换组件（如换推理引擎）

---

### 1.2 项目结构规范

```
localai-studio/
├── client/                 # React 前端
│   ├── src/
│   │   ├── components/    # 可复用组件
│   │   ├── pages/         # 页面组件
│   │   ├── store/         # Zustand 状态
│   │   ├── hooks/         # 自定义 Hooks
│   │   ├── utils/         # 工具函数
│   │   └── types/         # TypeScript 类型
│   ├── public/
│   └── package.json
│
├── server/                 # FastAPI 后端
│   ├── api/
│   │   ├── routes/        # API 路由
│   │   ├── models/        # 数据模型
│   │   └── services/      # 业务逻辑
│   ├── core/              # 核心配置
│   ├── utils/             # 工具函数
│   └── main.py
│
├── electron/               # Electron 主进程
│   ├── main.js
│   ├── preload.js
│   └── package.json
│
├── models/                 # 模型存储
│   └── (自动下载)
│
├── docs/                   # 文档
│   ├── API.md
│   ├── 开发指南.md
│   └── 用户手册.md
│
└── scripts/                # 构建脚本
    ├── build.py
    └── release.py
```

**关键原则**：
- 📁 按功能分组，不是按类型
- 📝 每个文件夹有 README.md 说明
- 🔧 工具函数放在 utils，业务逻辑放在 services

---

## 💻 二、前端开发最佳实践

### 2.1 组件设计规范

```tsx
// ✅ 好的组件设计
// components/Chat/ChatMessage.tsx

interface ChatMessageProps {
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  isStreaming?: boolean;
}

export const ChatMessage: React.FC<ChatMessageProps> = ({
  role,
  content,
  timestamp,
  isStreaming = false
}) => {
  // 1. 早返回
  if (!content) return null;
  
  // 2. 纯函数，无副作用
  const formattedTime = formatTime(timestamp);
  
  // 3. 单一职责
  return (
    <div className={`message ${role}`}>
      <div className="content">
        <Markdown>{content}</Markdown>
        {isStreaming && <Cursor />}
      </div>
      <div className="timestamp">{formattedTime}</div>
    </div>
  );
};
```

**组件设计原则**：
1. **单一职责** - 一个组件只做一件事
2. **Props 接口清晰** - 用 TypeScript 定义
3. **纯函数** - 避免副作用
4. **可复用** - 通过 Props 配置行为

---

### 2.2 状态管理最佳实践（Zustand）

```typescript
// store/chatStore.ts

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

interface ChatState {
  // 状态
  messages: Message[];
  isLoading: boolean;
  currentModel: string;
  
  // 动作
  addMessage: (message: Message) => void;
  clearMessages: () => void;
  setModel: (model: string) => void;
  sendMessage: (content: string) => Promise<void>;
}

export const useChatStore = create<ChatState>()(
  persist(
    (set, get) => ({
      messages: [],
      isLoading: false,
      currentModel: 'qwen-0.5b',
      
      addMessage: (message) =>
        set((state) => ({
          messages: [...state.messages, message]
        })),
      
      clearMessages: () => set({ messages: [] }),
      
      setModel: (model) => set({ currentModel: model }),
      
      sendMessage: async (content) => {
        // 添加用户消息
        const userMessage: Message = {
          id: Date.now().toString(),
          role: 'user',
          content,
          timestamp: new Date()
        };
        
        set((state) => ({
          messages: [...state.messages, userMessage],
          isLoading: true
        }));
        
        // 调用 API
        try {
          const response = await fetch('/api/chat/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              messages: [...get().messages, userMessage],
              model: get().currentModel
            })
          });
          
          // 处理流式响应
          const reader = response.body?.getReader();
          const aiMessage: Message = {
            id: (Date.now() + 1).toString(),
            role: 'assistant',
            content: '',
            timestamp: new Date()
          };
          
          set((state) => ({
            messages: [...state.messages, aiMessage]
          }));
          
          // 流式更新
          while (true) {
            const { done, value } = await reader!.read();
            if (done) break;
            
            const chunk = new TextDecoder().decode(value);
            set((state) => ({
              messages: state.messages.map(msg =>
                msg.id === aiMessage.id
                  ? { ...msg, content: msg.content + chunk }
                  : msg
              )
            }));
          }
        } finally {
          set({ isLoading: false });
        }
      }
    }),
    {
      name: 'chat-storage', // localStorage 键名
      partialize: (state) => ({
        messages: state.messages.slice(-50), // 只存最近 50 条
        currentModel: state.currentModel
      })
    }
  )
);
```

**状态管理原则**：
1. **集中管理** - 相关状态放在一起
2. **持久化** - 重要状态存 localStorage
3. **类型安全** - 用 TypeScript 定义
4. **限制大小** - 避免存储过多数据

---

### 2.3 流式输出最佳实践

```tsx
// hooks/useStream.ts

export const useStream = () => {
  const [isStreaming, setIsStreaming] = useState(false);
  
  const stream = useCallback(async (
    url: string,
    data: any,
    onChunk: (chunk: string) => void,
    onComplete: () => void,
    onError: (error: Error) => void
  ) => {
    setIsStreaming(true);
    
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      });
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      
      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      
      while (true) {
        const { done, value } = await reader!.read();
        if (done) break;
        
        const chunk = decoder.decode(value);
        onChunk(chunk);
      }
      
      onComplete();
    } catch (error) {
      onError(error as Error);
    } finally {
      setIsStreaming(false);
    }
  }, []);
  
  return { stream, isStreaming };
};

// 使用示例
const { stream, isStreaming } = useStream();

stream(
  '/api/chat/stream',
  { messages, model },
  (chunk) => setContent(prev => prev + chunk),
  () => console.log('完成'),
  (error) => console.error(error)
);
```

**流式处理要点**：
1. **错误处理** - 捕获网络和解析错误
2. **状态管理** - 跟踪流式状态
3. **资源清理** - 确保 reader 正确关闭
4. **用户反馈** - 显示加载状态

---

## 🐍 三、后端开发最佳实践

### 3.1 FastAPI 路由规范

```python
# server/api/routes/chat.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import asyncio

router = APIRouter(prefix="/api", tags=["chat"])

# 请求模型
class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    model: str = "qwen-0.5b"
    temperature: float = 0.7
    max_tokens: Optional[int] = None

# 流式响应
from fastapi.responses import StreamingResponse

@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """流式聊天接口"""
    
    # 1. 参数验证
    if not request.messages:
        raise HTTPException(status_code=400, detail="消息不能为空")
    
    # 2. 模型检查
    model = get_model(request.model)
    if not model:
        raise HTTPException(status_code=404, detail="模型不存在")
    
    # 3. 生成器函数
    async def generate():
        try:
            for chunk in model.generate_stream(
                messages=request.messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens
            ):
                yield chunk
                await asyncio.sleep(0)  # 让出事件循环
        except Exception as e:
            yield f"[ERROR] {str(e)}"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )

@router.get("/models")
async def list_models():
    """获取可用模型列表"""
    models = get_available_models()
    return {"models": models}
```

**API 设计原则**：
1. **RESTful 风格** - 资源导向的 URL 设计
2. **类型验证** - Pydantic 模型验证输入
3. **错误处理** - 清晰的错误信息
4. **文档自动生成** - FastAPI 自动生成 Swagger

---

### 3.2 模型管理最佳实践

```python
# server/api/services/model_manager.py

from typing import Dict, Optional
import threading
from pathlib import Path

class ModelManager:
    """单例模式管理模型"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance.models: Dict[str, any] = {}
                    cls._instance.loading: Dict[str, bool] = {}
        return cls._instance
    
    def load_model(self, model_path: str) -> bool:
        """加载模型到内存"""
        model_id = Path(model_path).name
        
        # 避免重复加载
        if model_id in self.models:
            return True
        
        # 避免重复加载中
        if model_id in self.loading:
            return False
        
        try:
            self.loading[model_id] = True
            
            # 加载模型（示例）
            from llama_cpp import Llama
            model = Llama(
                model_path=model_path,
                n_ctx=4096,
                n_threads=4
            )
            
            self.models[model_id] = model
            return True
            
        except Exception as e:
            print(f"加载模型失败：{e}")
            return False
            
        finally:
            self.loading.pop(model_id, None)
    
    def get_model(self, model_id: str) -> Optional[any]:
        """获取已加载的模型"""
        return self.models.get(model_id)
    
    def unload_model(self, model_id: str) -> bool:
        """卸载模型释放内存"""
        if model_id in self.models:
            del self.models[model_id]
            return True
        return False
    
    def list_models(self) -> List[Dict]:
        """列出所有可用模型"""
        return [
            {
                "id": model_id,
                "loaded": model_id in self.models,
                "loading": model_id in self.loading
            }
            for model_id in self._scan_model_directory()
        ]
    
    def _scan_model_directory(self) -> List[str]:
        """扫描模型目录"""
        model_dir = Path("models")
        if not model_dir.exists():
            return []
        
        return [
            d.name for d in model_dir.iterdir()
            if d.is_dir() and any(d.glob("*.gguf"))
        ]

# 全局单例
model_manager = ModelManager()
```

**模型管理要点**：
1. **单例模式** - 避免重复加载
2. **线程安全** - 多线程访问保护
3. **懒加载** - 需要时才加载
4. **内存管理** - 支持卸载释放

---

### 3.3 错误处理最佳实践

```python
# server/core/exceptions.py

from fastapi import HTTPException, status

class ModelNotFoundError(HTTPException):
    def __init__(self, model_id: str):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"模型 '{model_id}' 不存在"
        )

class ModelLoadError(HTTPException):
    def __init__(self, model_id: str, reason: str):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"模型 '{model_id}' 加载失败：{reason}"
        )

class InferenceError(HTTPException):
    def __init__(self, message: str):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"推理错误：{message}"
        )

# 使用示例
@router.post("/chat")
async def chat(request: ChatRequest):
    try:
        model = model_manager.get_model(request.model)
        if not model:
            raise ModelNotFoundError(request.model)
        
        response = model.generate(request.messages)
        return {"content": response}
        
    except ModelNotFoundError as e:
        raise e
    except Exception as e:
        raise InferenceError(str(e))
```

**错误处理原则**：
1. **自定义异常** - 清晰的错误类型
2. **详细错误信息** - 帮助用户理解问题
3. **统一处理** - 全局异常处理器
4. **日志记录** - 记录错误堆栈

---

## 🔒 四、安全最佳实践

### 4.1 输入验证

```python
# server/api/validators.py

from pydantic import BaseModel, validator, Field
import re

class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    model: str = Field(..., max_length=100)
    temperature: float = Field(ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, ge=1, le=10000)
    
    @validator('messages')
    def validate_messages(cls, v):
        if not v:
            raise ValueError("消息不能为空")
        if len(v) > 100:
            raise ValueError("消息数量不能超过 100 条")
        for msg in v:
            if len(msg.content) > 10000:
                raise ValueError("单条消息不能超过 10000 字符")
        return v
    
    @validator('model')
    def validate_model(cls, v):
        # 防止路径遍历攻击
        if '..' in v or v.startswith('/'):
            raise ValueError("无效的模型名称")
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError("模型名称只能包含字母、数字、下划线和连字符")
        return v
```

**安全要点**：
1. **长度限制** - 防止 DoS 攻击
2. **字符过滤** - 防止注入攻击
3. **路径验证** - 防止路径遍历
4. **类型检查** - 防止类型混淆

---

### 4.2 本地存储安全

```typescript
// client/utils/storage.ts

// ✅ 好的做法
export const storage = {
  // 敏感数据加密存储
  setSecure: (key: string, value: string) => {
    const encrypted = CryptoJS.AES.encrypt(value, SECRET_KEY).toString();
    localStorage.setItem(key, encrypted);
  },
  
  getSecure: (key: string): string | null => {
    const encrypted = localStorage.getItem(key);
    if (!encrypted) return null;
    
    try {
      const decrypted = CryptoJS.AES.decrypt(encrypted, SECRET_KEY).toString(CryptoJS.enc.Utf8);
      return decrypted || null;
    } catch {
      return null;
    }
  },
  
  // 非敏感数据直接存储
  set: (key: string, value: any) => {
    localStorage.setItem(key, JSON.stringify(value));
  },
  
  get: (key: string): any => {
    const value = localStorage.getItem(key);
    return value ? JSON.parse(value) : null;
  }
};

// 使用示例
storage.setSecure('api-key', 'sk-xxx'); // 敏感数据
storage.set('theme', 'dark'); // 非敏感数据
```

**存储安全原则**：
1. **敏感数据加密** - API Key、密码等
2. **最小化存储** - 只存必要数据
3. **定期清理** - 清理过期数据
4. **不存明文密码** - 绝不存储

---

## ⚡ 五、性能优化最佳实践

### 5.1 前端性能优化

```tsx
// ✅ 使用 React.memo 避免不必要的重渲染
const ChatMessage = React.memo(({ message }: { message: Message }) => {
  return <div>{message.content}</div>;
});

// ✅ 使用 useMemo 缓存计算结果
const filteredMessages = useMemo(() => {
  return messages.filter(m => m.role === 'user');
}, [messages]);

// ✅ 使用 useCallback 缓存函数
const handleSend = useCallback((content: string) => {
  // 处理发送
}, []);

// ✅ 虚拟列表（大量消息时）
import { FixedSizeList } from 'react-window';

const MessageList = ({ messages }) => (
  <FixedSizeList
    height={600}
    itemCount={messages.length}
    itemSize={100}
  >
    {({ index, style }) => (
      <div style={style}>
        <ChatMessage message={messages[index]} />
      </div>
    )}
  </FixedSizeList>
);

// ✅ 懒加载组件
const Settings = lazy(() => import('./Settings'));

// 使用 Suspense
<Suspense fallback={<Loading />}>
  <Settings />
</Suspense>
```

**性能优化要点**：
1. **避免重渲染** - React.memo、useMemo、useCallback
2. **虚拟列表** - 大量数据时分页/虚拟
3. **代码分割** - 懒加载非关键组件
4. **图片优化** - 压缩、懒加载

---

### 5.2 后端性能优化

```python
# server/utils/cache.py

from functools import lru_cache
import hashlib

# ✅ 使用缓存
@lru_cache(maxsize=100)
def get_model_response(model_id: str, message_hash: str):
    """缓存模型响应"""
    model = model_manager.get_model(model_id)
    return model.generate(message_hash)

# ✅ 异步处理
import asyncio

async def process_batch(messages: List[str]):
    """批量异步处理"""
    tasks = [process_single(msg) for msg in messages]
    return await asyncio.gather(*tasks)

# ✅ 连接池（数据库）
from databases import Database

database = Database("sqlite:///localai.db")

# 启动时连接
@app.on_event("startup")
async def startup():
    await database.connect()

# 关闭时断开
@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()
```

**后端优化要点**：
1. **缓存** - 缓存重复计算
2. **异步** - IO 密集型用异步
3. **连接池** - 数据库连接复用
4. **批量处理** - 减少 IO 次数

---

### 5.3 模型推理优化

```python
# server/api/services/inference.py

class OptimizedInference:
    def __init__(self, model_path: str):
        from llama_cpp import Llama
        
        # ✅ 优化参数
        self.model = Llama(
            model_path=model_path,
            n_ctx=4096,        # 上下文长度
            n_threads=4,       # 线程数
            n_gpu_layers=0,    # GPU 层数（有 GPU 时调整）
            use_mlock=True,    # 锁定内存
            verbose=False      # 关闭详细日志
        )
    
    def generate_stream(self, messages, **kwargs):
        """流式生成"""
        # ✅ 使用生成器
        for token in self.model(
            self._format_messages(messages),
            max_tokens=kwargs.get('max_tokens', 1024),
            temperature=kwargs.get('temperature', 0.7),
            stream=True  # 启用流式
        ):
            yield token['choices'][0]['text']
    
    def _format_messages(self, messages):
        """格式化消息"""
        # ✅ 缓存格式化结果
        return "\n".join([
            f"{m['role']}: {m['content']}"
            for m in messages
        ])
```

**推理优化要点**：
1. **量化模型** - 使用 GGUF 量化版本（4bit/8bit）
2. **上下文管理** - 限制上下文长度
3. **批处理** - 批量推理提高效率
4. **GPU 加速** - 有 GPU 时启用

---

## 🧪 六、测试最佳实践

### 6.1 单元测试

```python
# tests/test_inference.py

import pytest
from server.api.services.inference import OptimizedInference

def test_model_load():
    """测试模型加载"""
    inference = OptimizedInference("models/test-model")
    assert inference.model is not None

def test_generate():
    """测试生成"""
    inference = OptimizedInference("models/test-model")
    response = inference.generate([{"role": "user", "content": "你好"}])
    assert isinstance(response, str)
    assert len(response) > 0

def test_generate_stream():
    """测试流式生成"""
    inference = OptimizedInference("models/test-model")
    chunks = list(inference.generate_stream([{"role": "user", "content": "你好"}]))
    assert len(chunks) > 0
    assert all(isinstance(chunk, str) for chunk in chunks)

@pytest.mark.asyncio
async def test_async_generation():
    """测试异步生成"""
    inference = OptimizedInference("models/test-model")
    response = await inference.generate_async([{"role": "user", "content": "你好"}])
    assert isinstance(response, str)
```

**测试原则**：
1. **测试命名清晰** - test_功能_场景
2. **单一职责** - 每个测试只测一件事
3. **独立运行** - 测试之间不依赖
4. **覆盖边界** - 测试边界条件

---

### 6.2 端到端测试

```typescript
// tests/e2e/chat.test.ts

import { test, expect } from '@playwright/test';

test('发送消息并接收回复', async ({ page }) => {
  // 1. 打开应用
  await page.goto('http://localhost:5173');
  
  // 2. 输入消息
  await page.fill('[data-testid="chat-input"]', '你好');
  
  // 3. 发送
  await page.click('[data-testid="send-button"]');
  
  // 4. 等待回复
  await page.waitForSelector('[data-testid="message"]:last-child');
  
  // 5. 验证回复
  const lastMessage = await page.locator('[data-testid="message"]:last-child');
  await expect(lastMessage).toBeVisible();
});

test('切换模型', async ({ page }) => {
  await page.goto('http://localhost:5173');
  
  // 打开模型选择器
  await page.click('[data-testid="model-selector"]');
  
  // 选择模型
  await page.click('[data-testid="model-qwen"]');
  
  // 验证切换
  const selectedModel = await page.locator('[data-testid="current-model"]');
  await expect(selectedModel).toHaveText('Qwen-0.5B');
});
```

**E2E 测试要点**：
1. **真实场景** - 模拟用户操作
2. **关键路径** - 测试核心功能
3. **数据验证** - 验证 UI 和数据
4. **自动化** - CI/CD 自动运行

---

## 📦 七、打包发布最佳实践

### 7.1 Electron 打包配置

```javascript
// electron-builder.config.js

module.exports = {
  appId: 'com.localai.studio',
  productName: 'LocalAI Studio',
  version: '1.0.0',
  
  // 文件包含
  files: [
    'client/dist/**/*',
    'electron/main.js',
    'electron/preload.js',
    'server-dist/**/*'
  ],
  
  // 额外资源
  extraResources: [
    {
      from: 'models/',
      to: 'models/',
      filter: ['**/*', '!**/*.bin'] // 排除大文件
    }
  ],
  
  // Windows 配置
  win: {
    target: [
      {
        target: 'nsis',
        arch: ['x64']
      }
    ],
    icon: 'icon.ico'
  },
  
  // NSIS 安装包配置
  nsis: {
    oneClick: false,
    allowToChangeInstallationDirectory: true,
    createDesktopShortcut: true,
    createStartMenuShortcut: true,
    installerIcon: 'icon.ico',
    uninstallerIcon: 'icon.ico',
    installerHeaderIcon: 'icon.ico',
    shortcutName: 'LocalAI Studio'
  },
  
  // macOS 配置
  mac: {
    target: 'dmg',
    icon: 'icon.icns',
    category: 'public.app-category.developer-tools',
    hardenedRuntime: true,
    gatekeeperAssess: false
  },
  
  // Linux 配置
  linux: {
    target: ['AppImage', 'deb'],
    icon: 'icon.png',
    category: 'Development'
  },
  
  // 自动更新
  publish: {
    provider: 'github',
    owner: 'your-username',
    repo: 'localai-studio'
  }
};
```

---

### 7.2 CI/CD 配置

```yaml
# .github/workflows/release.yml

name: Release

on:
  push:
    tags:
      - 'v*'

jobs:
  build:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [windows-latest, macos-latest, ubuntu-latest]
    
    steps:
      - name: Checkout
        uses: actions/checkout@v3
      
      - name: Setup Node
        uses: actions/setup-node@v3
        with:
          node-version: 18
      
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      
      - name: Install dependencies
        run: |
          npm ci
          pip install -r server/requirements.txt
      
      - name: Build frontend
        run: npm run build
        working-directory: client
      
      - name: Build backend
        run: pyinstaller server/main.py --onefile
      
      - name: Package Electron
        run: npm run electron:pack
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
      
      - name: Upload Release
        uses: softprops/action-gh-release@v1
        with:
          files: dist/*
```

---

## 📝 八、文档最佳实践

### 8.1 README.md 模板

```markdown
# LocalAI Studio

你的私人 AI 助手，数据不出门，免费 unlimited 使用

![Version](https://img.shields.io/badge/version-1.0.0-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Downloads](https://img.shields.io/github/downloads/your-username/localai-studio/total)

## ✨ 特性

- 🔐 **100% 本地运行** - 数据隐私保护
- 💰 **完全免费** - 无订阅费用
- 📶 **离线可用** - 无需联网
- 🚀 **低延迟** - 即时响应
- 🎯 **多模型支持** - Llama、Qwen、Mistral 等

## 📥 安装

### Windows

1. 下载 [LocalAI Studio Setup.exe](链接)
2. 双击运行
3. 完成安装

### macOS

1. 下载 [LocalAI Studio.dmg](链接)
2. 拖入 Applications
3. 启动应用

### Linux

```bash
# AppImage
chmod +x LocalAI\ Studio.AppImage
./LocalAI\ Studio.AppImage

# 或 deb
sudo dpkg -i localai-studio.deb
```

## 🚀 快速开始

1. 启动应用
2. 选择模型（首次使用会自动下载）
3. 开始对话

## 📸 截图

![截图 1](screenshots/chat.png)
![截图 2](screenshots/models.png)

## 🛠️ 开发

```bash
# 克隆项目
git clone https://github.com/your-username/localai-studio

# 安装依赖
npm install
pip install -r server/requirements.txt

# 启动开发环境
npm run dev
```

## 📖 文档

- [API 文档](docs/API.md)
- [开发指南](docs/开发指南.md)
- [用户手册](docs/用户手册.md)

## 🤝 贡献

欢迎贡献！查看 [贡献指南](CONTRIBUTING.md)

## 📄 许可证

MIT License

## 🙏 致谢

- [llama.cpp](https://github.com/ggerganov/llama.cpp)
- [FastAPI](https://fastapi.tiangolo.com/)
- [React](https://react.dev/)
```

---

## 🎯 九、总结：关键实践清单

### 必须做的（P0）

- [ ] 分层架构（前端/后端/推理）
- [ ] TypeScript 类型安全
- [ ] Zustand 状态管理
- [ ] FastAPI 路由规范
- [ ] 输入验证
- [ ] 错误处理
- [ ] 单元测试

### 应该做的（P1）

- [ ] 流式输出
- [ ] 模型管理（单例）
- [ ] 缓存优化
- [ ] 性能优化（React.memo 等）
- [ ] E2E 测试
- [ ] CI/CD

### 可以做的（P2）

- [ ] 自动更新
- [ ] 插件系统
- [ ] 主题切换
- [ ] 多语言支持
- [ ] 性能监控

---

## 💬 下一步

**需要我帮你做什么？**

A. 创建项目模板（包含以上最佳实践）  
B. 实现具体功能（如聊天、模型管理）  
C. 配置开发环境  
D. 编写测试用例  

告诉我你的选择！🚀
