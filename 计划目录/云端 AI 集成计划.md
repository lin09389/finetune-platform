# ☁️ 云端 AI 集成计划 - 结合项目现状

**制定时间**: 2026-03-08  
**项目状态**: 功能完整，可立即扩展云端 AI

---

## 📊 项目现状分析

### ✅ 已有基础设施

| 模块 | 状态 | 可复用内容 |
|------|------|-----------|
| **聊天系统** | ✅ 完整 | Chat.tsx、消息管理、流式输出 |
| **推理服务** | ✅ 完整 | inference.py、Ollama/HF 后端 |
| **API 结构** | ✅ 完整 | FastAPI 路由、错误处理 |
| **前端组件** | ✅ 完整 | Ant Design、代码预览 |
| **项目上下文** | ✅ 新增 | 扫描/索引/检索 |
| **Agent 模块** | ✅ 完整 | 文件操作、意图识别 |

### 📦 依赖检查

```
✅ httpx=0.26.0 (已安装) - 用于 API 调用
✅ requests=2.31.0 (已安装) - HTTP 客户端
✅ FastAPI=0.109.0 (已安装) - Web 框架
✅ Ant Design=5.12.0 (已安装) - UI 组件
```

### 🔧 需要新增的

```
❌ ai/gateway.py - AI 网关（统一接口）
❌ api/api_keys.py - API Key 管理
❌ api/cloud_chat.py - 云端聊天接口
❌ 前端 API Key 管理页面
```

---

## 🎯 集成目标

### 阶段 1：Minimax Coding Plan（优先级 P0）

**理由**：
- ✅ 你已有套餐，无需额外费用
- ✅ 编程能力强，辅助开发
- ✅ 国内可用，网络稳定
- ✅ 集成简单（30 分钟）

**功能**：
- [ ] 创建 `ai/gateway.py` (Minimax 适配器)
- [ ] 创建 `api/cloud_chat.py` (云端聊天接口)
- [ ] 前端添加 API Key 输入
- [ ] Chat 页面添加"云端 AI"开关

**预计时间**: 30-60 分钟

---

### 阶段 2：多服务商支持（优先级 P1）

**支持的服务商**：
- [ ] Minimax（已支持）
- [ ] 智谱 GLM
- [ ] 通义千问（可选）
- [ ] OpenAI（可选，需要翻墙）

**功能**：
- [ ] 扩展 gateway.py（多适配器）
- [ ] API Key 管理界面
- [ ] 服务商切换
- [ ] 模型选择

**预计时间**: 2-3 小时

---

### 阶段 3：深度集成（优先级 P2）

**功能**：
- [ ] 本地/云端自动切换
- [ ] 用量统计和监控
- [ ] 费用估算
- [ ] API Key 加密存储
- [ ] 项目上下文 + 云端 AI

**预计时间**: 3-4 小时

---

## 📝 详细实现计划

### 第 1 步：创建 AI 网关（30 分钟）

**文件**: `server/ai/gateway.py`

```python
"""
AI 网关 - 统一云端 AI 接口
"""
from typing import Dict, List, AsyncGenerator, Optional
from abc import ABC, abstractmethod
import httpx
import json


class AIProvider(ABC):
    """AI 服务商抽象基类"""

    @abstractmethod
    async def chat(
        self,
        messages: List[Dict],
        model: str,
        api_key: str,
        **kwargs
    ) -> str:
        """非流式聊天"""
        pass

    @abstractmethod
    async def stream(
        self,
        messages: List[Dict],
        model: str,
        api_key: str,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """流式聊天"""
        pass


class MinimaxProvider(AIProvider):
    """Minimax 适配器（含 Coding Plan）"""

    def __init__(self, coding_mode: bool = False):
        self.base_url = "https://api.minimax.chat/v1"
        self.coding_mode = coding_mode

    async def chat(
        self,
        messages: List[Dict],
        model: str = "abab6.5",
        api_key: str = "",
        **kwargs
    ) -> str:
        # Coding Plan 使用专用模型和参数
        if self.coding_mode:
            model = "abab6.5-chat"
            kwargs = {
                "temperature": 0.7,
                "max_tokens": 4096,
                "top_p": 0.95,
                **kwargs
            }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/text/chatcompletion_v2",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model,
                    "messages": messages,
                    **kwargs
                },
                timeout=60.0
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]

    async def stream(
        self,
        messages: List[Dict],
        model: str = "abab6.5",
        api_key: str = "",
        **kwargs
    ) -> AsyncGenerator[str, None]:
        if self.coding_mode:
            model = "abab6.5-chat"
            kwargs = {
                "temperature": 0.7,
                "max_tokens": 4096,
                "top_p": 0.95,
                **kwargs
            }

        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/text/chatcompletion_v2",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model,
                    "messages": messages,
                    "stream": True,
                    **kwargs
                },
                timeout=60.0
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            content = chunk["choices"][0]["delta"].get("content", "")
                            if content:
                                yield content
                        except:
                            continue


# 服务商注册表
PROVIDERS: Dict[str, AIProvider] = {
    "minimax": MinimaxProvider(coding_mode=False),
    "minimax-coding": MinimaxProvider(coding_mode=True),
}


async def get_provider(provider: str) -> AIProvider:
    """获取服务商实例"""
    if provider not in PROVIDERS:
        raise ValueError(f"不支持的服务商：{provider}")
    return PROVIDERS[provider]
```

**任务清单**:
- [ ] 创建 `server/ai/__init__.py`
- [ ] 创建 `server/ai/gateway.py`
- [ ] 测试导入

---

### 第 2 步：创建云端聊天 API（30 分钟）

**文件**: `server/api/cloud_chat.py`

```python
"""
云端 AI 聊天 API
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, AsyncGenerator
import json
import logging

from ai.gateway import get_provider

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/cloud", tags=["云端 AI"])


class CloudChatRequest(BaseModel):
    """云端聊天请求"""
    provider: str = Field(..., description="服务商：minimax/minimax-coding")
    api_key: str = Field(..., description="API Key")
    model: str = Field(default="abab6.5", description="模型")
    messages: List[Dict[str, str]] = Field(..., description="消息历史")
    temperature: float = Field(default=0.7, description="温度")
    max_tokens: Optional[int] = Field(default=None, description="最大 tokens")
    stream: bool = Field(default=True, description="是否流式输出")


class CloudChatResponse(BaseModel):
    """云端聊天响应"""
    success: bool
    content: str
    provider: str
    model: str


@router.post("/chat", response_model=CloudChatResponse)
async def cloud_chat(request: CloudChatRequest):
    """云端聊天（非流式）"""
    try:
        provider = await get_provider(request.provider)
        content = await provider.chat(
            messages=request.messages,
            model=request.model,
            api_key=request.api_key,
            temperature=request.temperature,
            max_tokens=request.max_tokens
        )

        return CloudChatResponse(
            success=True,
            content=content,
            provider=request.provider,
            model=request.model
        )
    except Exception as e:
        logger.error(f"云端聊天失败：{e}")
        raise HTTPException(500, f"聊天失败：{str(e)}")


@router.post("/chat/stream")
async def cloud_chat_stream(request: CloudChatRequest):
    """云端聊天（流式）"""
    try:
        provider = await get_provider(request.provider)

        async def generate():
            async for chunk in provider.stream(
                messages=request.messages,
                model=request.model,
                api_key=request.api_key,
                temperature=request.temperature,
                max_tokens=request.max_tokens
            ):
                yield f"data: {json.dumps({'content': chunk})}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream"
        )
    except Exception as e:
        logger.error(f"流式聊天失败：{e}")
        raise HTTPException(500, f"聊天失败：{str(e)}")


@router.get("/providers")
async def list_providers():
    """列出可用的服务商"""
    return {
        "providers": [
            {
                "id": "minimax",
                "name": "Minimax",
                "models": ["abab6.5", "abab6", "abab5.5"],
                "coding_models": ["abab6.5-chat"]
            }
        ]
    }
```

**注册路由**:
修改 `server/main.py`:
```python
from api import cloud_chat  # 添加导入

# 注册路由
app.include_router(cloud_chat, prefix="/cloud", tags=["云端 AI"])
```

**任务清单**:
- [ ] 创建 `server/api/cloud_chat.py`
- [ ] 修改 `server/main.py` 注册路由
- [ ] 测试 API 端点

---

### 第 3 步：前端 API Key 管理（30 分钟）

**文件**: `client/src/pages/APIKeyManager.tsx`

```tsx
import { useState } from 'react'
import { Card, Input, Button, Space, Modal, App, Select, Alert } from 'antd'
import { PlusOutlined, SaveOutlined } from '@ant-design/icons'

const { TextArea } = Input

const PROVIDERS = [
  { value: 'minimax', label: 'Minimax' },
  { value: 'minimax-coding', label: 'Minimax Coding (编程)' },
]

interface APIKeyConfig {
  provider: string
  api_key: string
}

interface APIKeyManagerProps {
  onSave?: (config: APIKeyConfig) => void
  onCancel?: () => void
}

export const APIKeyManager: React.FC<APIKeyManagerProps> = ({
  onSave,
  onCancel
}) => {
  const { message } = App.useApp()
  const [provider, setProvider] = useState('minimax-coding')
  const [apiKey, setApiKey] = useState('')

  const handleSave = () => {
    if (!apiKey.trim()) {
      message.error('请输入 API Key')
      return
    }

    // 保存到本地存储
    const config = { provider, api_key: apiKey }
    localStorage.setItem('cloud_ai_key', JSON.stringify(config))

    message.success('API Key 已保存')
    onSave?.(config)
  }

  return (
    <Card
      title="☁️ 云端 AI 配置"
      extra={
        <Button icon={<SaveOutlined />} onClick={handleSave}>
          保存
        </Button>
      }
    >
      <Alert
        message="Minimax Coding Plan"
        description="使用你的 Minimax 编程套餐，享受更强的代码生成能力"
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
      />

      <Space direction="vertical" style={{ width: '100%' }} size="large">
        <div>
          <div style={{ marginBottom: 8 }}>服务商</div>
          <Select
            value={provider}
            onChange={setProvider}
            options={PROVIDERS}
            style={{ width: '100%' }}
          />
        </div>

        <div>
          <div style={{ marginBottom: 8 }}>
            API Key
            <span style={{ color: '#999', fontSize: 12, marginLeft: 8 }}>
              格式：group_id:api_key
            </span>
          </div>
          <TextArea
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="请输入 Minimax API Key，例如：1234567890:abcdefghijklmnop"
            rows={3}
          />
        </div>

        <Alert
          message="如何获取 API Key？"
          description={
            <ol style={{ margin: 0, paddingLeft: 20 }}>
              <li>访问 https://api.minimax.chat</li>
              <li>登录账号</li>
              <li>进入"控制台" → "API Key 管理"</li>
              <li>创建并复制 API Key</li>
            </ol>
          }
          type="success"
          showIcon
        />
      </Space>
    </Card>
  )
}
```

**任务清单**:
- [ ] 创建 `client/src/pages/APIKeyManager.tsx`
- [ ] 测试组件渲染

---

### 第 4 步：集成到 Chat 页面（30 分钟）

**修改**: `client/src/pages/Chat.tsx`

在现有代码基础上添加：

```tsx
// 在 imports 中添加
import { APIKeyManager } from './APIKeyManager'

// 添加状态
const [useCloudAI, setUseCloudAI] = useState(false)
const [cloudAIConfig, setCloudAIConfig] = useState<APIKeyConfig | null>(null)
const [configModalOpen, setConfigModalOpen] = useState(false)

// 加载保存的配置
useEffect(() => {
  const saved = localStorage.getItem('cloud_ai_key')
  if (saved) {
    try {
      setCloudAIConfig(JSON.parse(saved))
    } catch (e) {
      console.error('加载配置失败', e)
    }
  }
}, [])

// 发送消息时添加云端 AI 逻辑
const handleSend = async () => {
  if (useCloudAI && cloudAIConfig) {
    // 使用云端 AI
    await sendCloudMessage()
  } else {
    // 使用本地 AI
    await sendLocalMessage()
  }
}

const sendCloudMessage = async () => {
  if (!cloudAIConfig) return

  setLoading(true)
  try {
    const response = await fetch('http://127.0.0.1:8000/cloud/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        provider: cloudAIConfig.provider,
        api_key: cloudAIConfig.api_key,
        messages: messages.map(m => ({ role: m.role, content: m.content }))
      })
    })

    // 处理流式响应...
  } catch (error) {
    message.error('云端 AI 调用失败')
  } finally {
    setLoading(false)
  }
}

// 在 UI 中添加云端 AI 开关
<Card
  title="AI 对话"
  extra={
    <Space>
      <Button
        type={useCloudAI ? 'primary' : 'default'}
        onClick={() => setConfigModalOpen(true)}
        icon={useCloudAI ? <CloudOutlined /> : <RobotOutlined />}
      >
        {useCloudAI ? '☁️ 云端 AI' : '🤖 本地 AI'}
      </Button>
    </Space>
  }
>
```

**任务清单**:
- [ ] 修改 Chat.tsx 添加云端 AI 开关
- [ ] 添加配置弹窗
- [ ] 实现消息发送逻辑
- [ ] 测试完整流程

---

## 🗓️ 时间计划

### 方案 A：快速集成（推荐）

**总时间**: 2 小时

| 步骤 | 时间 | 产出 |
|------|------|------|
| 1. AI 网关 | 30 分钟 | gateway.py |
| 2. 云端 API | 30 分钟 | cloud_chat.py |
| 3. API Key 管理 | 30 分钟 | APIKeyManager.tsx |
| 4. Chat 集成 | 30 分钟 | 完整功能 |

**今晚就可以用！**

---

### 方案 B：完整实现

**总时间**: 4-6 小时

| 步骤 | 时间 | 产出 |
|------|------|------|
| 方案 A 全部内容 | 2 小时 | 基础功能 |
| 5. API Key 数据库存储 | 1 小时 | api_keys.py |
| 6. 多服务商支持 | 1 小时 | GLM/Qwen 适配器 |
| 7. 用量统计 | 1 小时 | 监控面板 |
| 8. 加密存储 | 1 小时 | 安全增强 |

**适合：需要完整功能**

---

## 📋 立即开始（方案 A）

### 准备工作（5 分钟）

```bash
# 1. 获取 Minimax API Key
访问：https://api.minimax.chat
登录 → 控制台 → API Key 管理 → 创建 Key
复制：group_id:api_key

# 2. 确认项目结构
cd C:\Users\JHJ\Desktop\finetune-platform

# 3. 创建必要目录
mkdir server\ai
```

### 执行步骤

```
19:00-19:05  准备工作
19:05-19:35  第 1 步：创建 AI 网关
19:35-20:05  第 2 步：创建云端 API
20:05-20:35  第 3 步：前端 API Key 管理
20:35-21:05  第 4 步：集成到 Chat
21:05-21:30  测试和优化

21:30        ✅ 完成！可以使用 Minimax Coding Plan
```

---

## ✅ 验收标准

### 功能验收

- [ ] 能成功输入并保存 API Key
- [ ] 切换到"云端 AI"模式
- [ ] 发送消息得到 Minimax 回复
- [ ] 流式输出正常
- [ ] 错误处理正常

### 性能验收

- [ ] 响应时间 < 3 秒
- [ ] 流式输出流畅
- [ ] 无内存泄漏

---

## 🚨 可能的问题和解决方案

### 问题 1：API Key 格式错误

**现象**: 调用失败，返回 401

**解决**: 
- 确认格式：`group_id:api_key`
- 中间有冒号分隔
- 两个部分都要保留

### 问题 2：网络连接超时

**现象**: 请求超时

**解决**:
- 检查网络
- Minimax 国内可直接访问
- 增加 timeout 参数

### 问题 3：额度不足

**现象**: 返回额度不足错误

**解决**:
- 登录官网查看套餐
- 充值或续费
- 切换回本地 AI

---

## 📊 成本估算

### Minimax Coding Plan

```
套餐费用：约 ¥99-199/月
包含额度：通常足够个人使用
超额费用：¥0.01-0.03/1k tokens

个人使用：
- 轻度（每天 10 次）：套餐内
- 中度（每天 50 次）：套餐内
- 重度（每天 200 次）：可能超额 ¥20-50
```

### 对比本地 AI

```
云端 AI：
✅ 无需硬件
✅ 模型最强
✅ 按需付费
❌ 长期贵

本地 AI：
✅ 免费
✅ 隐私好
❌ 需要硬件
❌ 模型有限

建议：混合使用
- 简单任务 → 本地
- 复杂编程 → 云端
```

---

## 🎯 你的决定

**A. 立即开始（推荐）**
- 我帮你写完整代码
- 2 小时完成
- 今晚就能用 Minimax Coding Plan

**B. 先看详细文档**
- 查看完整 API 文档
- 了解所有参数
- 再决定

**C. 调整方案**
- 有其他需求
- 想先测试 API
- 预算考虑

**D. 暂缓**
- 先用本地 AI
- 以后再说

---

<div align="center">

## 🚀 快速总结

**现状**: 项目基础设施完整，可立即扩展云端 AI

**优势**: 
- ✅ httpx 已安装
- ✅ FastAPI 路由完善
- ✅ 前端组件齐全
- ✅ 你已有 Minimax 套餐

**计划**: 2 小时快速集成
- 30 分钟：AI 网关
- 30 分钟：云端 API
- 30 分钟：前端管理
- 30 分钟：Chat 集成

**产出**: 可使用 Minimax Coding Plan 的完整功能

**现在就开始？告诉我你的选择！** 💪

</div>
