# 🧠 本地 AI 推理平台 - 长期记忆功能实现指南

## 🎯 什么是长期记忆

### 概念

```
短期记忆 = 当前对话上下文（有限）
长期记忆 = 跨对话的持久化记忆（无限）

示例：
用户：我叫小明，喜欢 Python 开发
AI:  好的，我记住了

（一周后）
用户：我适合做什么项目？
AI:  小明，根据你的 Python 开发背景，我建议...
     ↑
     这就是长期记忆
```

---

## 📊 技术架构

### 整体架构

```
┌─────────────────────────────────────────────────────┐
│                    用户对话                          │
└─────────────────────┬───────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────┐
│              记忆管理模块 (Memory Manager)           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │
│  │  短期记忆   │  │  长期记忆   │  │  记忆检索   │ │
│  │  (上下文)   │  │  (向量库)   │  │  (相似度)   │ │
│  └─────────────┘  └─────────────┘  └─────────────┘ │
└─────────────────────┬───────────────────────────────┘
                      │
         ┌────────────┼────────────┐
         ▼            ▼            ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│  对话历史   │ │  向量数据库  │ │  用户档案   │
│  (SQLite)   │ │ (LanceDB)   │ │  (JSON)     │
└─────────────┘ └─────────────┘ └─────────────┘
```

---

## 🗄️ 一、存储方案选择

### 方案对比

| 方案 | 优点 | 缺点 | 推荐度 |
|------|------|------|--------|
| **SQLite + 向量插件** | 简单、单一文件 | 向量搜索性能一般 | ⭐⭐⭐ |
| **LanceDB** | 轻量、快速、本地 | 需要额外依赖 | ⭐⭐⭐⭐⭐ |
| **Chroma** | 功能丰富 | 较重、依赖多 | ⭐⭐⭐ |
| **FAISS** | Facebook 出品、快速 | 需要自己封装 | ⭐⭐⭐⭐ |
| **纯文件系统** | 最简单 | 无法语义搜索 | ⭐⭐ |

### 推荐方案：LanceDB

**为什么选择 LanceDB**：
```
✅ 轻量级（~20MB）
✅ 完全本地（无需服务器）
✅ 语义搜索（向量相似度）
✅ 持久化（自动保存）
✅ Python 原生支持
✅ 免费开源
```

---

## 💻 二、完整实现方案

### 2.1 安装依赖

```bash
# 后端依赖
pip install lancedb
pip install sentence-transformers
pip install sqlite3  # 通常已安装

# 前端依赖
npm install @lancedb/lancedb  # 可选，前端直接用 API
```

---

### 2.2 数据库设计

```python
# server/memory/database.py

import sqlite3
import lancedb
from datetime import datetime
from typing import List, Optional, Dict
from dataclasses import dataclass
from pathlib import Path

@dataclass
class Memory:
    """记忆数据结构"""
    id: str
    content: str              # 记忆内容
    embedding: List[float]    # 向量嵌入
    category: str             # 分类（用户信息/偏好/事实/事件）
    importance: float         # 重要程度 (0-1)
    created_at: datetime      # 创建时间
    last_accessed: datetime   # 最后访问时间
    access_count: int         # 访问次数

class MemoryDatabase:
    """记忆数据库管理"""
    
    def __init__(self, data_dir: str = "./data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # 初始化 SQLite（存储元数据）
        self.sqlite_conn = sqlite3.connect(
            self.data_dir / "memory.db",
            check_same_thread=False
        )
        self._init_sqlite()
        
        # 初始化 LanceDB（向量搜索）
        self.lancedb_conn = lancedb.connect(self.data_dir / "vectors")
        self._init_lancedb()
    
    def _init_sqlite(self):
        """初始化 SQLite 表结构"""
        cursor = self.sqlite_conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                category TEXT NOT NULL,
                importance REAL DEFAULT 0.5,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                access_count INTEGER DEFAULT 0
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id TEXT PRIMARY KEY,
                profile_data TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_category 
            ON memories(category)
        """)
        
        self.sqlite_conn.commit()
    
    def _init_lancedb(self):
        """初始化 LanceDB 表结构"""
        # 如果表不存在，创建它
        if "memories" not in self.lancedb_conn.table_names():
            # 创建示例数据来定义 schema
            sample_data = [{
                "id": "example",
                "vector": [0.0] * 384,  # sentence-transformers 维度
                "content": "example",
                "category": "example"
            }]
            self.lancedb_conn.create_table("memories", sample_data)
    
    def add_memory(
        self,
        content: str,
        embedding: List[float],
        category: str = "general",
        importance: float = 0.5
    ) -> str:
        """添加新记忆"""
        import uuid
        
        memory_id = str(uuid.uuid4())
        now = datetime.now()
        
        # 写入 SQLite
        cursor = self.sqlite_conn.cursor()
        cursor.execute("""
            INSERT INTO memories (id, content, category, importance, created_at, last_accessed)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (memory_id, content, category, importance, now, now))
        
        # 写入 LanceDB（向量）
        table = self.lancedb_conn.open_table("memories")
        table.add([{
            "id": memory_id,
            "vector": embedding,
            "content": content,
            "category": category
        }])
        
        self.sqlite_conn.commit()
        return memory_id
    
    def search_memories(
        self,
        query_embedding: List[float],
        category: Optional[str] = None,
        limit: int = 5
    ) -> List[Dict]:
        """语义搜索记忆"""
        table = self.lancedb_conn.open_table("memories")
        
        # 构建搜索
        search_query = table.search(query_embedding, vector_column_name="vector")
        
        # 如果有分类过滤，先获取所有记忆再过滤
        results = search_query.limit(limit * 2).to_list()  # 多取一些用于过滤
        
        # 过滤分类
        if category:
            results = [r for r in results if r.get("category") == category]
        
        # 获取完整信息（从 SQLite）
        cursor = self.sqlite_conn.cursor()
        memories = []
        for result in results[:limit]:
            cursor.execute("""
                SELECT id, content, category, importance, created_at, last_accessed, access_count
                FROM memories WHERE id = ?
            """, (result["id"],))
            row = cursor.fetchone()
            if row:
                memories.append({
                    "id": row[0],
                    "content": row[1],
                    "category": row[2],
                    "importance": row[3],
                    "created_at": row[4],
                    "last_accessed": row[5],
                    "access_count": row[6] + 1,  # 访问次数 +1
                    "relevance": result.get("_distance", 0)
                })
                
                # 更新访问时间和次数
                cursor.execute("""
                    UPDATE memories 
                    SET last_accessed = ?, access_count = ?
                    WHERE id = ?
                """, (datetime.now(), row[6] + 1, row[0]))
        
        self.sqlite_conn.commit()
        return memories
    
    def get_user_profile(self, user_id: str) -> Dict:
        """获取用户档案"""
        cursor = self.sqlite_conn.cursor()
        cursor.execute("""
            SELECT profile_data FROM user_profiles WHERE user_id = ?
        """, (user_id,))
        row = cursor.fetchone()
        
        if row:
            import json
            return json.loads(row[0])
        return {}
    
    def update_user_profile(self, user_id: str, profile_data: Dict):
        """更新用户档案"""
        import json
        
        cursor = self.sqlite_conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO user_profiles (user_id, profile_data, updated_at)
            VALUES (?, ?, ?)
        """, (user_id, json.dumps(profile_data), datetime.now()))
        self.sqlite_conn.commit()
    
    def forget_memory(self, memory_id: str):
        """删除记忆（用户要求遗忘）"""
        cursor = self.sqlite_conn.cursor()
        cursor.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        
        table = self.lancedb_conn.open_table("memories")
        table.delete(f"id = '{memory_id}'")
        
        self.sqlite_conn.commit()
    
    def get_memories_by_importance(
        self,
        min_importance: float = 0.7,
        limit: int = 20
    ) -> List[Dict]:
        """获取重要记忆"""
        cursor = self.sqlite_conn.cursor()
        cursor.execute("""
            SELECT id, content, category, importance, created_at
            FROM memories
            WHERE importance >= ?
            ORDER BY importance DESC, access_count DESC
            LIMIT ?
        """, (min_importance, limit))
        
        return [
            {
                "id": row[0],
                "content": row[1],
                "category": row[2],
                "importance": row[3],
                "created_at": row[4]
            }
            for row in cursor.fetchall()
        ]
```

---

### 2.3 嵌入模型（Embedding）

```python
# server/memory/embedding.py

from typing import List, Optional
from sentence_transformers import SentenceTransformer
import numpy as np

class EmbeddingModel:
    """文本嵌入模型"""
    
    def __init__(self, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"):
        """
        初始化嵌入模型
        
        推荐模型：
        - paraphrase-multilingual-MiniLM-L12-v2: 支持中文，384 维，轻量
        - text2vec-base-chinese: 中文优化，768 维
        - all-MiniLM-L6-v2: 英文，384 维，最快
        """
        self.model_name = model_name
        self.model: Optional[SentenceTransformer] = None
    
    def load(self):
        """加载模型到内存"""
        if self.model is None:
            self.model = SentenceTransformer(self.model_name)
    
    def embed(self, text: str) -> List[float]:
        """将文本转换为向量"""
        if self.model is None:
            self.load()
        
        embedding = self.model.encode(text, convert_to_numpy=True)
        return embedding.tolist()
    
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """批量嵌入"""
        if self.model is None:
            self.load()
        
        embeddings = self.model.encode(texts, convert_to_numpy=True)
        return embeddings.tolist()
    
    def similarity(self, embedding1: List[float], embedding2: List[float]) -> float:
        """计算两个向量的相似度（余弦相似度）"""
        v1 = np.array(embedding1)
        v2 = np.array(embedding2)
        
        similarity = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))
        return float(similarity)

# 全局单例
embedding_model = EmbeddingModel()
```

---

### 2.4 记忆管理器

```python
# server/memory/manager.py

from typing import List, Dict, Optional
from datetime import datetime
import re

from .database import MemoryDatabase, Memory
from .embedding import embedding_model

class MemoryManager:
    """记忆管理器 - 核心逻辑"""
    
    def __init__(self, data_dir: str = "./data"):
        self.db = MemoryDatabase(data_dir)
        self.embedding_model = embedding_model
        self.embedding_model.load()
        
        # 记忆分类
        self.categories = [
            "user_info",      # 用户个人信息（名字、职业等）
            "preference",     # 用户偏好（喜欢的语言、工具等）
            "fact",          # 事实性知识
            "event",         # 事件记录
            "skill",         # 技能/能力
            "general"        # 其他
        ]
    
    def extract_memories(
        self,
        conversation: List[Dict],
        user_id: str = "default"
    ) -> List[str]:
        """
        从对话中提取需要记忆的信息
        
        Args:
            conversation: 对话历史 [{"role": "user/assistant", "content": "..."}]
            user_id: 用户 ID
        
        Returns:
            提取的记忆列表
        """
        memories = []
        
        # 合并对话内容
        full_text = "\n".join([f"{m['role']}: {m['content']}" for m in conversation])
        
        # 规则 1: 提取用户明确表达的信息
        # 模式："我叫 XX"、"我是 XX"、"我喜欢 XX"等
        patterns = [
            (r"我叫 (.*?)[，,.。!！]", "user_info", "用户的名字是{0}"),
            (r"我是 (.*?)[，,.。!！]", "user_info", "用户是{0}"),
            (r"我喜欢 (.*?)[，,.。!！]", "preference", "用户喜欢{0}"),
            (r"我讨厌 (.*?)[，,.。!！]", "preference", "用户讨厌{0}"),
            (r"我在 (.*?)工作", "user_info", "用户在{0}工作"),
            (r"我住在 (.*?)[，,.。!！]", "user_info", "用户住在{0}"),
            (r"我是 (.*?)学生", "user_info", "用户是学生，专业/学校是{0}"),
            (r"我学 (.*?)[专业|方向]", "user_info", "用户学习{0}"),
            (r"我用 (.*?)编程", "preference", "用户使用{0}编程"),
            (r"我常用 (.*?)[，,.。!！]", "preference", "用户常用{0}"),
        ]
        
        for pattern, category, template in patterns:
            matches = re.findall(pattern, full_text, re.IGNORECASE)
            for match in matches:
                memory_content = template.format(match)
                memories.append({
                    "content": memory_content,
                    "category": category
                })
        
        # 规则 2: 使用 LLM 提取（更智能）
        llm_memories = self._extract_with_llm(conversation)
        memories.extend(llm_memories)
        
        # 去重并存储
        unique_memories = []
        seen_contents = set()
        
        for memory in memories:
            if memory["content"] not in seen_contents:
                seen_contents.add(memory["content"])
                unique_memories.append(memory)
        
        # 存储到数据库
        for memory in unique_memories:
            embedding = self.embedding_model.embed(memory["content"])
            importance = self._calculate_importance(memory["category"])
            
            self.db.add_memory(
                content=memory["content"],
                embedding=embedding,
                category=memory["category"],
                importance=importance
            )
        
        return [m["content"] for m in unique_memories]
    
    def _extract_with_llm(self, conversation: List[Dict]) -> List[Dict]:
        """使用 LLM 提取记忆（更智能但更慢）"""
        # 这里可以调用本地模型来提取
        # 简化版本：基于关键词
        
        memories = []
        
        # 检查是否有重要信息
        important_keywords = [
            "记住", "别忘了", "Important", "note that",
            "我的", "我家", "我公司", "我学校"
        ]
        
        for message in conversation:
            if message["role"] == "user":
                content = message["content"]
                
                # 检查是否包含重要关键词
                if any(kw in content for kw in important_keywords):
                    # 提取相关句子
                    sentences = re.split(r'[.。!！?？]', content)
                    for sentence in sentences:
                        if sentence.strip() and len(sentence.strip()) > 10:
                            memories.append({
                                "content": sentence.strip(),
                                "category": "general"
                            })
        
        return memories
    
    def _calculate_importance(self, category: str) -> float:
        """计算记忆重要程度"""
        importance_map = {
            "user_info": 0.9,      # 用户信息最重要
            "preference": 0.8,     # 偏好很重要
            "skill": 0.7,          # 技能重要
            "fact": 0.5,           # 事实一般
            "event": 0.4,          # 事件较不重要
            "general": 0.3         # 其他最不重要
        }
        return importance_map.get(category, 0.5)
    
    def retrieve_relevant_memories(
        self,
        query: str,
        user_id: str = "default",
        limit: int = 5
    ) -> List[Dict]:
        """检索与当前查询相关的记忆"""
        # 生成查询向量
        query_embedding = self.embedding_model.embed(query)
        
        # 搜索记忆
        memories = self.db.search_memories(
            query_embedding=query_embedding,
            limit=limit
        )
        
        return memories
    
    def get_context_with_memory(
        self,
        query: str,
        conversation: List[Dict],
        user_id: str = "default"
    ) -> str:
        """
        获取包含记忆的对话上下文
        
        Returns:
            格式化的上下文字符串
        """
        # 检索相关记忆
        memories = self.retrieve_relevant_memories(query, user_id, limit=5)
        
        # 构建上下文
        context_parts = []
        
        # 1. 添加相关记忆
        if memories:
            memory_text = "相关记忆:\n"
            for mem in memories:
                memory_text += f"- {mem['content']}\n"
            context_parts.append(memory_text)
        
        # 2. 添加对话历史（最近 10 轮）
        recent_conversation = conversation[-10:]
        if recent_conversation:
            conv_text = "对话历史:\n"
            for msg in recent_conversation:
                conv_text += f"{msg['role']}: {msg['content']}\n"
            context_parts.append(conv_text)
        
        return "\n".join(context_parts)
    
    def get_user_summary(self, user_id: str = "default") -> Dict:
        """获取用户摘要（用于快速了解用户）"""
        # 获取用户档案
        profile = self.db.get_user_profile(user_id)
        
        # 获取重要记忆
        important_memories = self.db.get_memories_by_importance(
            min_importance=0.7,
            limit=20
        )
        
        # 分类整理
        categories = {}
        for mem in important_memories:
            cat = mem["category"]
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(mem["content"])
        
        return {
            "profile": profile,
            "memories_by_category": categories,
            "total_memories": len(important_memories)
        }
    
    def update_user_profile(self, user_id: str, key: str, value: str):
        """更新用户档案"""
        profile = self.db.get_user_profile(user_id)
        profile[key] = value
        self.db.update_user_profile(user_id, profile)
    
    def forget_memory(self, memory_id: str):
        """删除记忆"""
        self.db.forget_memory(memory_id)
    
    def clear_all_memories(self, user_id: str = "default"):
        """清除所有记忆（谨慎使用）"""
        # 实际项目中需要实现这个方法
        pass
```

---

### 2.5 API 接口

```python
# server/api/routes/memory.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict
from datetime import datetime

from ...memory.manager import MemoryManager

router = APIRouter(prefix="/api/memory", tags=["memory"])

# 初始化记忆管理器
memory_manager = MemoryManager(data_dir="./data")

# 请求模型
class ExtractMemoryRequest(BaseModel):
    conversation: List[Dict[str, str]]
    user_id: str = "default"

class RetrieveMemoryRequest(BaseModel):
    query: str
    user_id: str = "default"
    limit: int = 5

class MemoryResponse(BaseModel):
    id: str
    content: str
    category: str
    importance: float
    created_at: str
    relevance: Optional[float] = None

# API 端点
@router.post("/extract")
async def extract_memories(request: ExtractMemoryRequest):
    """从对话中提取记忆"""
    try:
        memories = memory_manager.extract_memories(
            conversation=request.conversation,
            user_id=request.user_id
        )
        return {
            "success": True,
            "memories": memories,
            "count": len(memories)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/retrieve")
async def retrieve_memories(request: RetrieveMemoryRequest):
    """检索相关记忆"""
    try:
        memories = memory_manager.retrieve_relevant_memories(
            query=request.query,
            user_id=request.user_id,
            limit=request.limit
        )
        
        return {
            "success": True,
            "memories": [
                MemoryResponse(
                    id=m["id"],
                    content=m["content"],
                    category=m["category"],
                    importance=m["importance"],
                    created_at=str(m["created_at"]),
                    relevance=m.get("relevance")
                )
                for m in memories
            ],
            "count": len(memories)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/summary")
async def get_user_summary(user_id: str = "default"):
    """获取用户记忆摘要"""
    try:
        summary = memory_manager.get_user_summary(user_id)
        return {
            "success": True,
            "summary": summary
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{memory_id}")
async def delete_memory(memory_id: str):
    """删除记忆"""
    try:
        memory_manager.forget_memory(memory_id)
        return {
            "success": True,
            "message": "记忆已删除"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/list")
async def list_memories(
    user_id: str = "default",
    category: Optional[str] = None,
    limit: int = 50
):
    """列出所有记忆"""
    try:
        # 获取重要记忆
        memories = memory_manager.db.get_memories_by_importance(
            min_importance=0.3,
            limit=limit
        )
        
        # 按分类过滤
        if category:
            memories = [m for m in memories if m["category"] == category]
        
        return {
            "success": True,
            "memories": memories,
            "count": len(memories)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/profile")
async def update_profile(
    user_id: str = "default",
    key: str = None,
    value: str = None
):
    """更新用户档案"""
    try:
        if key and value:
            memory_manager.update_user_profile(user_id, key, value)
        return {
            "success": True,
            "message": "档案已更新"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

---

### 2.6 集成到聊天 API

```python
# server/api/routes/chat.py (修改版)

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
import asyncio

from ...memory.manager import MemoryManager

router = APIRouter(prefix="/api", tags=["chat"])

memory_manager = MemoryManager(data_dir="./data")

class ChatRequest(BaseModel):
    messages: List[Dict[str, str]]
    model: str = "qwen-0.5b"
    user_id: str = "default"
    use_memory: bool = True  # 是否使用长期记忆

@router.post("/chat")
async def chat(request: ChatRequest):
    """聊天接口（带长期记忆）"""
    
    # 1. 如果有长期记忆，获取相关记忆
    context = ""
    if request.use_memory and len(request.messages) > 0:
        # 获取最后一条用户消息
        last_user_message = request.messages[-1]["content"]
        
        # 检索相关记忆
        context = memory_manager.get_context_with_memory(
            query=last_user_message,
            conversation=request.messages,
            user_id=request.user_id
        )
    
    # 2. 构建带记忆的 prompt
    if context:
        system_prompt = f"""你是一个有帮助的 AI 助手。

{context}

请根据以上记忆和对话历史，给用户一个有帮助的回答。
如果记忆中有关于用户的信息，请自然地使用这些信息。
"""
    else:
        system_prompt = "你是一个有帮助的 AI 助手。"
    
    # 3. 调用模型
    model = get_model(request.model)
    response = model.generate(
        messages=request.messages,
        system_prompt=system_prompt
    )
    
    # 4. 从对话中提取新记忆（异步）
    asyncio.create_task(
        memory_manager.extract_memories(
            conversation=request.messages + [{"role": "assistant", "content": response}],
            user_id=request.user_id
        )
    )
    
    return {"content": response}

@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """流式聊天接口（带长期记忆）"""
    
    # 1. 获取相关记忆
    context = ""
    if request.use_memory and len(request.messages) > 0:
        last_user_message = request.messages[-1]["content"]
        context = memory_manager.get_context_with_memory(
            query=last_user_message,
            conversation=request.messages,
            user_id=request.user_id
        )
    
    # 2. 构建 prompt
    if context:
        system_prompt = f"""你是一个有帮助的 AI 助手。

{context}

请根据以上记忆和对话历史，给用户一个有帮助的回答。
"""
    else:
        system_prompt = "你是一个有帮助的 AI 助手。"
    
    # 3. 流式生成
    async def generate():
        model = get_model(request.model)
        
        for chunk in model.generate_stream(
            messages=request.messages,
            system_prompt=system_prompt
        ):
            yield chunk
        
        # 4. 异步提取记忆
        asyncio.create_task(
            memory_manager.extract_memories(
                conversation=request.messages,
                user_id=request.user_id
            )
        )
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream"
    )
```

---

## 🎨 三、前端实现

### 3.1 记忆管理组件

```tsx
// client/src/components/Memory/MemoryManager.tsx

import React, { useState, useEffect } from 'react';
import { useChatStore } from '../../store/chatStore';

interface Memory {
  id: string;
  content: string;
  category: string;
  importance: number;
  created_at: string;
}

export const MemoryManager: React.FC = () => {
  const [memories, setMemories] = useState<Memory[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  
  // 获取记忆列表
  const fetchMemories = async () => {
    setLoading(true);
    try {
      const response = await fetch('/api/memory/list');
      const data = await response.json();
      setMemories(data.memories);
    } catch (error) {
      console.error('获取记忆失败:', error);
    } finally {
      setLoading(false);
    }
  };
  
  // 删除记忆
  const deleteMemory = async (memoryId: string) => {
    if (!confirm('确定要删除这条记忆吗？')) return;
    
    try {
      await fetch(`/api/memory/${memoryId}`, { method: 'DELETE' });
      setMemories(memories.filter(m => m.id !== memoryId));
    } catch (error) {
      console.error('删除记忆失败:', error);
    }
  };
  
  // 按分类过滤
  const filteredMemories = selectedCategory === 'all'
    ? memories
    : memories.filter(m => m.category === selectedCategory);
  
  // 分类图标
  const categoryIcons: Record<string, string> = {
    user_info: '👤',
    preference: '❤️',
    fact: '📚',
    event: '📅',
    skill: '🛠️',
    general: '📝'
  };
  
  return (
    <div className="memory-manager">
      <div className="memory-header">
        <h2>长期记忆</h2>
        <button onClick={fetchMemories} disabled={loading}>
          {loading ? '加载中...' : '刷新'}
        </button>
      </div>
      
      {/* 分类过滤 */}
      <div className="category-filter">
        <button
          className={selectedCategory === 'all' ? 'active' : ''}
          onClick={() => setSelectedCategory('all')}
        >
          全部
        </button>
        {['user_info', 'preference', 'fact', 'skill', 'general'].map(cat => (
          <button
            key={cat}
            className={selectedCategory === cat ? 'active' : ''}
            onClick={() => setSelectedCategory(cat)}
          >
            {categoryIcons[cat]} {cat}
          </button>
        ))}
      </div>
      
      {/* 记忆列表 */}
      <div className="memory-list">
        {filteredMemories.map(memory => (
          <div key={memory.id} className="memory-item">
            <div className="memory-content">
              <span className="category-icon">{categoryIcons[memory.category]}</span>
              <p>{memory.content}</p>
            </div>
            <div className="memory-meta">
              <span className="importance">
                重要度：{'⭐'.repeat(Math.round(memory.importance))}
              </span>
              <span className="date">
                {new Date(memory.created_at).toLocaleDateString('zh-CN')}
              </span>
              <button
                className="delete-btn"
                onClick={() => deleteMemory(memory.id)}
              >
                删除
              </button>
            </div>
          </div>
        ))}
      </div>
      
      {filteredMemories.length === 0 && (
        <div className="empty-state">
          <p>暂无记忆</p>
          <p className="hint">对话中提到的重要信息会自动保存为记忆</p>
        </div>
      )}
    </div>
  );
};
```

---

### 3.2 聊天中显示记忆提示

```tsx
// client/src/components/Chat/MemoryHint.tsx

import React from 'react';

interface MemoryHintProps {
  memories: string[];
  onDismiss: () => void;
}

export const MemoryHint: React.FC<MemoryHintProps> = ({ memories, onDismiss }) => {
  if (memories.length === 0) return null;
  
  return (
    <div className="memory-hint">
      <div className="memory-hint-header">
        <span>💡 AI 记住了这些信息</span>
        <button onClick={onDismiss}>×</button>
      </div>
      <ul>
        {memories.map((memory, index) => (
          <li key={index}>{memory}</li>
        ))}
      </ul>
      <a href="/memory" className="manage-link">
        管理记忆 →
      </a>
    </div>
  );
};
```

---

### 3.3 样式

```css
/* client/src/styles/memory.css */

.memory-manager {
  padding: 20px;
  max-width: 800px;
  margin: 0 auto;
}

.memory-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.category-filter {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 20px;
}

.category-filter button {
  padding: 8px 16px;
  border: 1px solid #ddd;
  border-radius: 20px;
  background: white;
  cursor: pointer;
  transition: all 0.2s;
}

.category-filter button.active {
  background: #2563eb;
  color: white;
  border-color: #2563eb;
}

.memory-list {
  display: flex;
  flex-direction: column;
  gap: 15px;
}

.memory-item {
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 16px;
  transition: box-shadow 0.2s;
}

.memory-item:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.memory-content {
  display: flex;
  gap: 12px;
  margin-bottom: 12px;
}

.category-icon {
  font-size: 24px;
  flex-shrink: 0;
}

.memory-content p {
  margin: 0;
  color: #1f2937;
  line-height: 1.6;
}

.memory-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  color: #6b7280;
}

.importance {
  color: #f59e0b;
}

.delete-btn {
  padding: 4px 12px;
  border: 1px solid #ef4444;
  border-radius: 6px;
  background: white;
  color: #ef4444;
  cursor: pointer;
  font-size: 12px;
}

.delete-btn:hover {
  background: #ef4444;
  color: white;
}

.empty-state {
  text-align: center;
  padding: 40px;
  color: #6b7280;
}

.empty-state .hint {
  font-size: 14px;
  margin-top: 8px;
}

/* 记忆提示 */
.memory-hint {
  background: #fef3c7;
  border: 1px solid #f59e0b;
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 16px;
}

.memory-hint-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  font-weight: 600;
  color: #92400e;
}

.memory-hint ul {
  margin: 8px 0;
  padding-left: 20px;
  color: #78350f;
}

.manage-link {
  display: inline-block;
  margin-top: 8px;
  color: #2563eb;
  text-decoration: none;
  font-size: 14px;
}
```

---

## ⚡ 四、性能优化

### 4.1 批量嵌入

```python
# 优化：批量处理而不是单个处理
async def extract_memories_batch(
    self,
    conversations: List[List[Dict]],
    user_ids: List[str]
):
    """批量提取记忆"""
    # 1. 提取所有记忆内容
    all_memories = []
    for conv in conversations:
        memories = self._extract_from_conversation(conv)
        all_memories.extend(memories)
    
    # 2. 批量生成嵌入
    if all_memories:
        contents = [m["content"] for m in all_memories]
        embeddings = self.embedding_model.embed_batch(contents)
        
        # 3. 批量存储
        for memory, embedding in zip(all_memories, embeddings):
            self.db.add_memory(
                content=memory["content"],
                embedding=embedding.tolist(),
                category=memory["category"]
            )
```

### 4.2 记忆过期策略

```python
def cleanup_old_memories(self, days: int = 90):
    """清理过期记忆"""
    from datetime import datetime, timedelta
    
    cutoff_date = datetime.now() - timedelta(days=days)
    
    cursor = self.sqlite_conn.cursor()
    cursor.execute("""
        DELETE FROM memories
        WHERE importance < 0.3
        AND created_at < ?
        AND access_count = 0
    """, (cutoff_date,))
    
    deleted_count = cursor.rowcount
    self.sqlite_conn.commit()
    
    return deleted_count
```

### 4.3 缓存热点记忆

```python
from functools import lru_cache

class MemoryManager:
    @lru_cache(maxsize=100)
    def retrieve_relevant_memories_cached(
        self,
        query_hash: str,
        limit: int = 5
    ) -> List[Dict]:
        """缓存的记忆检索"""
        # 实际检索逻辑
        pass
```

---

## 📊 五、测试示例

```python
# tests/test_memory.py

import pytest
from server.memory.manager import MemoryManager
from server.memory.embedding import embedding_model

@pytest.fixture
def memory_manager():
    return MemoryManager(data_dir="./test_data")

def test_extract_memories(memory_manager):
    """测试记忆提取"""
    conversation = [
        {"role": "user", "content": "我叫小明，是一名 Python 开发者"},
        {"role": "assistant", "content": "你好小明！很高兴认识你"},
    ]
    
    memories = memory_manager.extract_memories(conversation)
    
    assert len(memories) > 0
    assert any("小明" in m for m in memories)
    assert any("Python" in m for m in memories)

def test_retrieve_memories(memory_manager):
    """测试记忆检索"""
    # 先添加记忆
    conversation = [
        {"role": "user", "content": "我喜欢用 React 开发前端"},
    ]
    memory_manager.extract_memories(conversation)
    
    # 检索
    memories = memory_manager.retrieve_relevant_memories(
        query="前端开发用什么框架"
    )
    
    assert len(memories) > 0
    assert any("React" in m["content"] for m in memories)

def test_forget_memory(memory_manager):
    """测试删除记忆"""
    conversation = [
        {"role": "user", "content": "这是一条测试记忆"},
    ]
    memories = memory_manager.extract_memories(conversation)
    
    # 获取记忆 ID
    all_memories = memory_manager.db.get_memories_by_importance(limit=1)
    memory_id = all_memories[0]["id"]
    
    # 删除
    memory_manager.forget_memory(memory_id)
    
    # 验证删除
    remaining = memory_manager.db.get_memories_by_importance(limit=10)
    assert not any(m["id"] == memory_id for m in remaining)
```

---

## 📋 六、实现清单

### P0（必须）

- [ ] 数据库设计（SQLite + LanceDB）
- [ ] 嵌入模型集成
- [ ] 记忆管理器核心逻辑
- [ ] 记忆提取 API
- [ ] 记忆检索 API
- [ ] 集成到聊天 API

### P1（重要）

- [ ] 前端记忆管理界面
- [ ] 记忆中提示组件
- [ ] 用户档案功能
- [ ] 记忆分类过滤

### P2（可选）

- [ ] LLM 智能提取
- [ ] 记忆过期清理
- [ ] 批量处理优化
- [ ] 记忆导入导出

---

## 💬 总结

### 技术栈

```
存储：SQLite（元数据）+ LanceDB（向量）
嵌入：sentence-transformers（多语言支持）
管理：自定义 MemoryManager
前端：React 组件
```

### 核心流程

```
1. 对话 → 提取记忆 → 存储
2. 新查询 → 检索记忆 → 构建上下文 → 回答
3. 用户 → 查看/管理/删除记忆
```

### 用户体验

```
- 自动提取（用户无感知）
- 智能检索（自然使用记忆）
- 透明管理（用户可查看删除）
```

---

## 🚀 下一步

**需要我帮你做什么？**

A. 创建完整的项目代码结构  
B. 实现具体的某个模块  
C. 设计数据库 Schema  
D. 写前端组件  

告诉我你的选择！🧠
