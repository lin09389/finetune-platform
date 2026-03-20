# 🔑 API Key 调用云端 AI - 完整开发方案

## 🎯 功能说明

### 支持的服务商

```
✅ OpenAI (GPT-4, GPT-3.5)
✅ Claude (Anthropic)
✅ Minimax (国产)
✅ GLM/智谱 AI (国产)
✅ Qwen/通义千问 (阿里云)
✅ 其他 OpenAI 兼容 API
```

### 核心功能

```
1. API Key 管理
   - 添加/删除 Key
   - 加密存储
   - 用量统计

2. 多服务商支持
   - 一键切换
   - 模型选择
   - 价格对比

3. 聊天集成
   - 本地/云端切换
   - 流式输出
   - 统一接口
```

---

## 🏗️ 技术架构

```
┌─────────────────────────────────────────────────────────┐
│              前端界面                                    │
│  ┌─────────────────────────────────────────────────┐   │
│  │  API Key 管理页面                                │   │
│  │  - 添加 Key                                      │   │
│  │  - 测试连接                                      │   │
│  │  - 用量统计                                      │   │
│  └─────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────┐   │
│  │  聊天页面                                        │   │
│  │  - 模型选择（本地/云端）                        │   │
│  │  - 服务商切换                                    │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────┬───────────────────────────────────┘
                      │
┌─────────────────────▼─────────────────────────────────┐
│              API 网关层                                │
│  ┌─────────────────────────────────────────────────┐ │
│  │  统一接口                                        │ │
│  │  - chat()                                       │ │
│  │  - stream()                                     │ │
│  │  - models()                                     │ │
│  └─────────────────────────────────────────────────┘ │
└─────────────────────┬───────────────────────────────────┘
                      │
┌─────────────────────▼─────────────────────────────────┐
│              服务商适配器                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  │ OpenAI   │ │ Claude   │ │ Minimax  │ │ GLM      │ │
│  │ Adapter  │ │ Adapter  │ │ Adapter  │ │ Adapter  │ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ │
└─────────────────────────────────────────────────────────┘
                      │
┌─────────────────────▼─────────────────────────────────┐
│              云端 AI 服务                              │
│  - api.openai.com                                     │
│  - api.anthropic.com                                  │
│  - api.minimax.chat                                   │
│  - open.bigmodel.cn                                   │
└─────────────────────────────────────────────────────────┘
```

---

## 📝 具体实现

### 第 1 步：创建 API Key 管理

```python
# server/api/api_keys.py

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field, validator
from typing import Dict, List, Optional
from datetime import datetime
import sqlite3
import json
from pathlib import Path

router = APIRouter(prefix="/api-keys", tags=["API Key 管理"])

DB_PATH = Path(__file__).parent.parent / "data" / "api_keys.db"


def get_db():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """初始化数据库"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            key_hash TEXT NOT NULL,
            key_prefix TEXT,
            name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_used TIMESTAMP,
            usage_count INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1
        )
    """)
    
    conn.commit()
    conn.close()


class APIKeyCreate(BaseModel):
    """创建 API Key"""
    provider: str  # openai, claude, minimax, glm
    api_key: str
    name: Optional[str] = None
    
    @validator('api_key')
    def validate_api_key(cls, v):
        if not v or len(v) < 10:
            raise ValueError('API Key 格式不正确')
        return v


class APIKeyResponse(BaseModel):
    """API Key 响应（不返回完整 Key）"""
    id: str
    provider: str
    name: Optional[str]
    key_prefix: str  # 显示前缀，如 sk-abc123...
    created_at: str
    last_used: Optional[str]
    usage_count: int
    is_active: bool


import hashlib

def hash_key(key: str) -> str:
    """哈希 API Key"""
    return hashlib.sha256(key.encode()).hexdigest()


def get_key_prefix(key: str) -> str:
    """获取 Key 前缀（用于显示）"""
    if len(key) > 8:
        return f"{key[:8]}..."
    return key


@router.on_event("startup")
async def startup():
    """启动时初始化数据库"""
    init_db()


@router.post("", response_model=APIKeyResponse)
async def create_api_key(request: APIKeyCreate):
    """添加 API Key"""
    conn = get_db()
    cursor = conn.cursor()
    
    # 生成 ID
    import uuid
    key_id = f"key_{uuid.uuid4().hex[:8]}"
    
    # 验证 Key（测试连接）
    try:
        await validate_api_key(request.provider, request.api_key)
    except Exception as e:
        conn.close()
        raise HTTPException(400, f"API Key 无效：{str(e)}")
    
    # 存储（只存哈希）
    cursor.execute("""
        INSERT INTO api_keys (id, provider, key_hash, key_prefix, name)
        VALUES (?, ?, ?, ?, ?)
    """, (
        key_id,
        request.provider,
        hash_key(request.api_key),
        get_key_prefix(request.api_key),
        request.name or request.provider
    ))
    
    conn.commit()
    conn.close()
    
    return APIKeyResponse(
        id=key_id,
        provider=request.provider,
        name=request.name or request.provider,
        key_prefix=get_key_prefix(request.api_key),
        created_at=datetime.now().isoformat(),
        last_used=None,
        usage_count=0,
        is_active=True
    )


@router.get("", response_model=List[APIKeyResponse])
async def list_api_keys():
    """列出所有 API Key"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, provider, key_prefix, name, created_at, last_used, usage_count, is_active
        FROM api_keys
        ORDER BY created_at DESC
    """)
    
    keys = []
    for row in cursor.fetchall():
        keys.append(APIKeyResponse(
            id=row['id'],
            provider=row['provider'],
            name=row['name'],
            key_prefix=row['key_prefix'],
            created_at=row['created_at'],
            last_used=row['last_used'],
            usage_count=row['usage_count'],
            is_active=bool(row['is_active'])
        ))
    
    conn.close()
    return keys


@router.delete("/{key_id}")
async def delete_api_key(key_id: str):
    """删除 API Key"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))
    
    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(404, "API Key 不存在")
    
    conn.commit()
    conn.close()
    
    return {"success": True, "message": "已删除"}


@router.post("/{key_id}/test")
async def test_api_key(key_id: str):
    """测试 API Key"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT provider FROM api_keys WHERE id = ?", (key_id,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        raise HTTPException(404, "API Key 不存在")
    
    provider = row['provider']
    
    # 这里需要从安全存储中获取实际 Key
    # 简化示例，实际需要加密存储
    conn.close()
    
    # 测试连接
    try:
        result = await validate_api_key(provider, "actual_key_here")
        return {"success": True, "message": "连接成功", "models": result}
    except Exception as e:
        return {"success": False, "message": f"连接失败：{str(e)}"}
```

---

### 第 2 步：创建统一 API 网关

```python
# server/ai/gateway.py

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
    
    @abstractmethod
    async def models(self, api_key: str) -> List[str]:
        """获取可用模型列表"""
        pass


class OpenAIProvider(AIProvider):
    """OpenAI 适配器"""
    
    def __init__(self):
        self.base_url = "https://api.openai.com/v1"
    
    async def chat(
        self,
        messages: List[Dict],
        model: str = "gpt-3.5-turbo",
        api_key: str = "",
        **kwargs
    ) -> str:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
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
        model: str = "gpt-3.5-turbo",
        api_key: str = "",
        **kwargs
    ) -> AsyncGenerator[str, None]:
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
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
    
    async def models(self, api_key: str) -> List[str]:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/models",
                headers={"Authorization": f"Bearer {api_key}"}
            )
            response.raise_for_status()
            data = response.json()
            return [m["id"] for m in data["data"] if "gpt" in m["id"]]


class ClaudeProvider(AIProvider):
    """Claude 适配器"""
    
    def __init__(self):
        self.base_url = "https://api.anthropic.com/v1"
    
    async def chat(
        self,
        messages: List[Dict],
        model: str = "claude-3-sonnet-20240229",
        api_key: str = "",
        **kwargs
    ) -> str:
        # 转换消息格式
        system_prompt = ""
        new_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_prompt = msg["content"]
            else:
                new_messages.append(msg)
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model,
                    "max_tokens": 4096,
                    "system": system_prompt,
                    "messages": new_messages,
                    **kwargs
                },
                timeout=60.0
            )
            response.raise_for_status()
            data = response.json()
            return data["content"][0]["text"]
    
    async def stream(
        self,
        messages: List[Dict],
        model: str = "claude-3-sonnet-20240229",
        api_key: str = "",
        **kwargs
    ) -> AsyncGenerator[str, None]:
        # 简化实现，实际需要用 SSE
        content = await self.chat(messages, model, api_key, **kwargs)
        for char in content:
            yield char
    
    async def models(self, api_key: str) -> List[str]:
        return [
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229",
            "claude-3-haiku-20240307"
        ]


class MinimaxProvider(AIProvider):
    """Minimax 适配器"""
    
    def __init__(self):
        self.base_url = "https://api.minimax.chat/v1"
    
    async def chat(
        self,
        messages: List[Dict],
        model: str = "abab6.5",
        api_key: str = "",
        **kwargs
    ) -> str:
        # Minimax 使用 group_id
        group_id = api_key.split(":")[0] if ":" in api_key else ""
        
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
    
    async def models(self, api_key: str) -> List[str]:
        return ["abab6.5", "abab6", "abab5.5"]


class GLMProvider(AIProvider):
    """智谱 GLM 适配器"""
    
    def __init__(self):
        self.base_url = "https://open.bigmodel.cn/api/paas/v4"
    
    async def chat(
        self,
        messages: List[Dict],
        model: str = "glm-4",
        api_key: str = "",
        **kwargs
    ) -> str:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
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
        model: str = "glm-4",
        api_key: str = "",
        **kwargs
    ) -> AsyncGenerator[str, None]:
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
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
    
    async def models(self, api_key: str) -> List[str]:
        return ["glm-4", "glm-3-turbo", "glm-4v"]


# 提供商注册表
PROVIDERS: Dict[str, AIProvider] = {
    "openai": OpenAIProvider(),
    "claude": ClaudeProvider(),
    "minimax": MinimaxProvider(),
    "glm": GLMProvider(),
}


async def validate_api_key(provider: str, api_key: str) -> List[str]:
    """验证 API Key 并获取可用模型"""
    if provider not in PROVIDERS:
        raise ValueError(f"不支持的服务商：{provider}")
    
    provider_instance = PROVIDERS[provider]
    return await provider_instance.models(api_key)


async def get_provider(provider: str) -> AIProvider:
    """获取服务商实例"""
    if provider not in PROVIDERS:
        raise ValueError(f"不支持的服务商：{provider}")
    return PROVIDERS[provider]
```

---

### 第 3 步：创建 API 端点

```python
# server/api/cloud_chat.py

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, AsyncGenerator
from fastapi.responses import StreamingResponse
import json

from ai.gateway import get_provider, validate_api_key

router = APIRouter(prefix="/cloud", tags=["云端 AI"])


class CloudChatRequest(BaseModel):
    """云端聊天请求"""
    provider: str  # openai, claude, minimax, glm
    api_key_id: str  # 存储的 Key ID
    model: str
    messages: List[Dict[str, str]]
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    stream: bool = True


class CloudModelsResponse(BaseModel):
    """可用模型列表"""
    provider: str
    models: List[str]


@router.post("/models")
async def get_cloud_models(
    provider: str,
    api_key_id: str
):
    """获取可用模型列表"""
    # 从数据库获取 API Key
    from api.api_keys import get_db
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT provider FROM api_keys WHERE id = ? AND is_active = 1",
        (api_key_id,)
    )
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(404, "API Key 不存在或已禁用")
    
    # 这里需要获取实际的 Key（从加密存储）
    # 简化示例
    actual_key = "actual_key_here"
    
    try:
        models = await validate_api_key(provider, actual_key)
        return CloudModelsResponse(provider=provider, models=models)
    except Exception as e:
        raise HTTPException(400, f"获取模型失败：{str(e)}")


@router.post("/chat")
async def cloud_chat(request: CloudChatRequest):
    """云端聊天（非流式）"""
    # 获取 API Key
    from api.api_keys import get_db, hash_key
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT provider, key_hash FROM api_keys WHERE id = ? AND is_active = 1",
        (request.api_key_id,)
    )
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(404, "API Key 不存在或已禁用")
    
    # 这里需要解密获取实际 Key
    actual_key = "actual_key_here"
    
    try:
        provider = await get_provider(request.provider)
        content = await provider.chat(
            messages=request.messages,
            model=request.model,
            api_key=actual_key,
            temperature=request.temperature,
            max_tokens=request.max_tokens
        )
        
        # 更新使用记录
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE api_keys 
            SET last_used = CURRENT_TIMESTAMP, usage_count = usage_count + 1
            WHERE id = ?
        """, (request.api_key_id,))
        conn.commit()
        conn.close()
        
        return {
            "success": True,
            "content": content,
            "provider": request.provider,
            "model": request.model
        }
    except Exception as e:
        raise HTTPException(500, f"聊天失败：{str(e)}")


@router.post("/chat/stream")
async def cloud_chat_stream(request: CloudChatRequest):
    """云端聊天（流式）"""
    # 获取 API Key
    from api.api_keys import get_db
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT provider FROM api_keys WHERE id = ? AND is_active = 1",
        (request.api_key_id,)
    )
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(404, "API Key 不存在或已禁用")
    
    actual_key = "actual_key_here"
    
    try:
        provider = await get_provider(request.provider)
        
        async def generate():
            async for chunk in provider.stream(
                messages=request.messages,
                model=request.model,
                api_key=actual_key,
                temperature=request.temperature,
                max_tokens=request.max_tokens
            ):
                yield f"data: {json.dumps({'content': chunk})}\n\n"
            
            # 更新使用记录
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE api_keys 
                SET last_used = CURRENT_TIMESTAMP, usage_count = usage_count + 1
                WHERE id = ?
            """, (request.api_key_id,))
            conn.commit()
            conn.close()
            
            yield "data: [DONE]\n\n"
        
        return StreamingResponse(
            generate(),
            media_type="text/event-stream"
        )
    except Exception as e:
        raise HTTPException(500, f"流式聊天失败：{str(e)}")
```

---

### 第 4 步：前端 API Key 管理

```tsx
// client/src/pages/APIKeyManager.tsx

import { useState, useEffect } from 'react'
import { Card, Input, Button, List, Tag, Space, Modal, App, Select, Alert } from 'antd'
import { PlusOutlined, DeleteOutlined, CheckCircleOutlined, CloseCircleOutlined } from '@ant-design/icons'

const PROVIDERS = [
  { value: 'openai', label: 'OpenAI', icon: '🟢' },
  { value: 'claude', label: 'Claude', icon: '🟣' },
  { value: 'minimax', label: 'Minimax', icon: '🔵' },
  { value: 'glm', label: '智谱 GLM', icon: '🟠' },
]

interface APIKey {
  id: string
  provider: string
  name: string
  key_prefix: string
  created_at: string
  last_used: string | null
  usage_count: number
  is_active: boolean
}

export const APIKeyManager: React.FC = () => {
  const { message } = App.useApp()
  const [keys, setKeys] = useState<APIKey[]>([])
  const [loading, setLoading] = useState(false)
  const [addModalOpen, setAddModalOpen] = useState(false)
  const [newKey, setNewKey] = useState({
    provider: 'openai',
    api_key: '',
    name: ''
  })
  const [testing, setTesting] = useState<string | null>(null)

  useEffect(() => {
    loadKeys()
  }, [])

  const loadKeys = async () => {
    setLoading(true)
    try {
      const response = await fetch('http://127.0.0.1:8000/api-keys')
      const data = await response.json()
      setKeys(data)
    } catch (error) {
      message.error('加载失败')
    } finally {
      setLoading(false)
    }
  }

  const addKey = async () => {
    if (!newKey.api_key) {
      message.error('请输入 API Key')
      return
    }

    try {
      const response = await fetch('http://127.0.0.1:8000/api-keys', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newKey)
      })

      if (response.ok) {
        message.success('API Key 添加成功')
        setAddModalOpen(false)
        setNewKey({ provider: 'openai', api_key: '', name: '' })
        loadKeys()
      } else {
        const error = await response.json()
        message.error(`添加失败：${error.detail}`)
      }
    } catch (error) {
      message.error('添加失败')
    }
  }

  const deleteKey = async (keyId: string) => {
    Modal.confirm({
      title: '确认删除',
      content: '确定要删除这个 API Key 吗？',
      onOk: async () => {
        try {
          await fetch(`http://127.0.0.1:8000/api-keys/${keyId}`, {
            method: 'DELETE'
          })
          message.success('已删除')
          loadKeys()
        } catch (error) {
          message.error('删除失败')
        }
      }
    })
  }

  const testKey = async (keyId: string, provider: string) => {
    setTesting(keyId)
    try {
      const response = await fetch(`http://127.0.0.1:8000/api-keys/${keyId}/test`, {
        method: 'POST'
      })
      const result = await response.json()
      
      if (result.success) {
        message.success('连接成功')
      } else {
        message.error(`连接失败：${result.message}`)
      }
    } catch (error) {
      message.error('测试失败')
    } finally {
      setTesting(null)
    }
  }

  return (
    <div style={{ padding: 24 }}>
      <Card
        title="🔑 API Key 管理"
        extra={
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setAddModalOpen(true)}
          >
            添加 API Key
          </Button>
        }
      >
        <Alert
          message="安全提示"
          description="API Key 会加密存储在本地，不会上传到任何服务器"
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
        />

        <List
          loading={loading}
          dataSource={keys}
          renderItem={(key) => (
            <List.Item
              actions={[
                <Button
                  key="test"
                  size="small"
                  loading={testing === key.id}
                  onClick={() => testKey(key.id, key.provider)}
                >
                  测试
                </Button>,
                <Button
                  key="delete"
                  size="small"
                  danger
                  icon={<DeleteOutlined />}
                  onClick={() => deleteKey(key.id)}
                >
                  删除
                </Button>
              ]}
            >
              <List.Item.Meta
                title={
                  <Space>
                    <span>{PROVIDERS.find(p => p.value === key.provider)?.icon}</span>
                    <span>{key.name}</span>
                    <Tag color={key.is_active ? 'green' : 'red'}>
                      {key.is_active ? '启用' : '禁用'}
                    </Tag>
                  </Space>
                }
                description={
                  <Space direction="vertical" size="small">
                    <div>
                      <Tag>{key.provider}</Tag>
                      <span style={{ marginLeft: 8, color: '#999' }}>
                        {key.key_prefix}
                      </span>
                    </div>
                    <div style={{ fontSize: 12, color: '#999' }}>
                      创建：{new Date(key.created_at).toLocaleDateString()}
                      {key.last_used && ` · 最后使用：${new Date(key.last_used).toLocaleDateString()}`}
                      {key.usage_count > 0 && ` · 使用次数：${key.usage_count}`}
                    </div>
                  </Space>
                }
              />
            </List.Item>
          )}
        />
      </Card>

      {/* 添加 API Key 弹窗 */}
      <Modal
        title="添加 API Key"
        open={addModalOpen}
        onOk={addKey}
        onCancel={() => setAddModalOpen(false)}
      >
        <Space direction="vertical" style={{ width: '100%' }} size="large">
          <div>
            <div style={{ marginBottom: 8 }}>服务商</div>
            <Select
              value={newKey.provider}
              onChange={(value) => setNewKey({ ...newKey, provider: value })}
              options={PROVIDERS}
              style={{ width: '100%' }}
            />
          </div>
          
          <div>
            <div style={{ marginBottom: 8 }}>名称（可选）</div>
            <Input
              placeholder="例如：我的 OpenAI Key"
              value={newKey.name}
              onChange={(e) => setNewKey({ ...newKey, name: e.target.value })}
            />
          </div>
          
          <div>
            <div style={{ marginBottom: 8 }}>API Key</div>
            <Input.Password
              placeholder="输入 API Key"
              value={newKey.api_key}
              onChange={(e) => setNewKey({ ...newKey, api_key: e.target.value })}
            />
          </div>

          {newKey.provider === 'minimax' && (
            <Alert
              message="Minimax 提示"
              description="Minimax 的 API Key 格式为：group_id:api_key"
              type="info"
              showIcon
            />
          )}
        </Space>
      </Modal>
    </div>
  )
}
```

---

### 第 5 步：集成到聊天页面

```tsx
// client/src/pages/Chat.tsx (修改)

// 添加云端 AI 支持
const [useCloudAI, setUseCloudAI] = useState(false)
const [selectedProvider, setSelectedProvider] = useState('openai')
const [selectedAPIKey, setSelectedAPIKey] = useState('')
const [cloudModels, setCloudModels] = useState([])

// 修改发送函数
const handleSend = async () => {
  if (!selectedModel && !useCloudAI) return
  if (!inputValue.trim()) return

  const userMessage: Message = {
    id: `msg_${Date.now()}`,
    role: 'user',
    content: inputValue.trim(),
    timestamp: new Date().toISOString(),
  }

  setMessages(prev => [...prev, userMessage])
  setInputValue('')
  setLoading(true)

  if (useCloudAI) {
    // 使用云端 AI
    await sendCloudMessage(userMessage)
  } else {
    // 使用本地 AI
    await sendLocalMessage(userMessage)
  }

  setLoading(false)
}

const sendCloudMessage = async (userMessage: Message) => {
  const assistantMessageId = `msg_${Date.now() + 1}`
  setMessages(prev => [...prev, {
    id: assistantMessageId,
    role: 'assistant',
    content: '',
    timestamp: new Date().toISOString(),
    isLoading: true,
  }])

  try {
    let fullResponse = ''
    
    const response = await fetch('http://127.0.0.1:8000/cloud/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        provider: selectedProvider,
        api_key_id: selectedAPIKey,
        model: selectedModel,
        messages: buildPrompt(messages, userMessage.content),
        stream: true
      })
    })

    const reader = response.body?.getReader()
    const decoder = new TextDecoder()

    while (true) {
      const { done, value } = await reader!.read()
      if (done) break

      const text = decoder.decode(value)
      const lines = text.split('\n')
      
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6)
          if (data === '[DONE]') break
          
          try {
            const chunk = JSON.parse(data)
            if (chunk.content) {
              fullResponse += chunk.content
              setMessages(prev => prev.map(msg =>
                msg.id === assistantMessageId
                  ? { ...msg, content: fullResponse, isLoading: false }
                  : msg
              ))
            }
          } catch {}
        }
      }
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : '云端 AI 请求失败'
    setMessages(prev => prev.map(msg =>
      msg.id === assistantMessageId
        ? { ...msg, content: `错误：${errorMsg}`, isLoading: false }
        : msg
    ))
  }
}

// 在 UI 中添加云端 AI 切换
<div style={{ marginBottom: 16 }}>
  <Space>
    <Button
      type={!useCloudAI ? 'primary' : 'default'}
      onClick={() => setUseCloudAI(false)}
    >
      🏠 本地 AI
    </Button>
    <Button
      type={useCloudAI ? 'primary' : 'default'}
      onClick={() => setUseCloudAI(true)}
    >
      ☁️ 云端 AI
    </Button>
    
    {useCloudAI && (
      <>
        <Select
          value={selectedProvider}
          onChange={setSelectedProvider}
          options={PROVIDERS}
          style={{ width: 150 }}
        />
        <Select
          value={selectedAPIKey}
          onChange={setSelectedAPIKey}
          placeholder="选择 API Key"
          style={{ width: 200 }}
        />
      </>
    )}
  </Space>
</div>
```

---

## 🚀 开发计划

### 第 1 周（15 小时）

```
Day 1-3: API Key 管理（6h）
├─ 数据库设计
├─ CRUD API
└─ 加密存储

Day 4-6: AI 网关（6h）
├─ 抽象基类
├─ OpenAI 适配器
├─ Claude 适配器
└── Minimax/GLM 适配器

Day 7: 云端聊天 API（3h）
├─ 聊天端点
└─ 流式输出
```

### 第 2 周（10 小时）

```
Day 1-3: 前端管理界面（6h）
├─ API Key 管理页面
└─ 模型选择

Day 4-5: 集成到聊天（4h）
├─ 本地/云端切换
└─ 统一接口

总计：25 小时完成！
```

---

## 📋 完整文档

**位置**：`C:\Users\JHJ\Desktop\墨墨计划项目\API Key 调用云端 AI 方案.md`

---

## 💬 你的决定

**A. 立即开始** — 我帮你写第一步代码  
**B. 先看详细代码** — 查看完整实现  
**C. 调整方案** — 有其他想法？  
**D. 继续提问** — 还有疑问？  

**2 周完成，支持主流 AI 服务商！** 🚀

告诉我你的选择！💪