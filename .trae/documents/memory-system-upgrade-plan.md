# 记忆系统改进升级方案

## 一、Supermemory 项目深度分析

### 1.1 项目概览

**项目信息**
- **名称**: supermemory
- **GitHub**: https://github.com/supermemoryai/supermemory
- **Star 数**: 16,923 ⭐
- **技术栈**: TypeScript, Cloudflare Workers, PostgreSQL, Drizzle ORM
- **定位**: AI 时代的记忆引擎，为 AI 应用提供通用记忆 API

**核心特性**
1. **知识图谱记忆** - 通过 `packages/memory-graph` 实现实体关系图谱
2. **多 SDK 支持** - 提供 OpenAI SDK、Python Agent Framework、Pipecat SDK 等
3. **浏览器扩展** - Chrome 扩展支持网页内容记忆
4. **MCP 协议** - 支持 Model Context Protocol，实现跨工具记忆共享
5. **云端部署** - 基于 Cloudflare Workers + PostgreSQL 的云原生架构
6. **向量搜索** - 支持语义相似度检索

### 1.2 架构亮点

```
supermemory/
├── packages/
│   ├── memory-graph/        # 知识图谱核心
│   ├── lib/                 # 核心库
│   │   ├── api.ts          # API 客户端
│   │   ├── queries.ts      # 查询逻辑
│   │   └── similarity.ts   # 相似度计算
│   ├── openai-sdk-python/  # Python SDK
│   └── agent-framework-python/  # Agent 框架
├── apps/
│   ├── web/                # Web 应用
│   ├── browser-extension/  # 浏览器扩展
│   └── mcp/                # MCP 服务器
└── skills/                 # 技能系统
```

**关键设计模式**

1. **知识图谱存储**
   - 实体提取器（Entity Extractor）识别对话中的实体
   - 关系生成器（Relations Generator）推断实体间关系
   - 图数据库存储实体-关系网络

2. **多级记忆架构**
   - 短期记忆：当前会话上下文
   - 长期记忆：向量数据库持久化
   - 工作记忆：当前推理状态

3. **跨平台同步**
   - MCP 协议实现跨工具记忆共享
   - 浏览器扩展自动捕获网页内容
   - 云端 API 统一管理

---

## 二、当前项目记忆系统现状分析

### 2.1 现有实现

**文件结构**
```
server/memory/
├── memory_service.py      # 记忆服务核心
├── memory_extractor.py    # 记忆提取器
└── models.py              # 数据模型
```

**核心功能**
1. **记忆提取** - 基于正则规则的提取
2. **记忆存储** - ChromaDB 向量存储
3. **记忆检索** - 语义相似度搜索
4. **记忆类型** - 7 种类型（个人/偏好/项目/技能/习惯/历史/知识）

### 2.2 存在的问题

| 问题类别 | 具体问题 | 影响 |
|---------|---------|------|
| **提取能力** | 仅依赖正则规则，无法理解复杂语义 | 提取准确率低 |
| **知识表示** | 扁平化存储，缺乏实体关系图谱 | 无法进行关联推理 |
| **记忆层次** | 只有长期记忆，无短期/工作记忆 | 上下文管理效率低 |
| **跨平台** | 无 MCP 协议支持 | 无法与其他 AI 工具共享 |
| **持久化** | 依赖本地 ChromaDB | 无法云端同步 |
| **记忆更新** | 无记忆合并/更新机制 | 可能产生重复记忆 |

---

## 三、改进升级方案

### 3.1 架构升级：三级记忆系统

```
┌─────────────────────────────────────────────────────────────┐
│                      Memory Manager                          │
├─────────────────┬─────────────────┬─────────────────────────┤
│   工作记忆       │   短期记忆       │      长期记忆           │
│ Working Memory  │ Short-term      │   Long-term Memory      │
├─────────────────┼─────────────────┼─────────────────────────┤
│ • 当前推理状态   │ • 最近 N 轮对话  │ • 知识图谱存储          │
│ • 临时变量      │ • 会话上下文     │ • 向量数据库            │
│ • 活跃实体      │ • 时间衰减       │ • 实体关系网络          │
│ • Redis/内存    │ • Redis 缓存    │ • PostgreSQL + pgvector │
└─────────────────┴─────────────────┴─────────────────────────┘
```

### 3.2 核心改进模块

#### 改进 1：知识图谱记忆系统

**参考**: supermemory 的 `packages/memory-graph`

**实现方案**:

```python
# server/memory/knowledge_graph.py

from dataclasses import dataclass
from typing import List, Dict, Optional, Set
from datetime import datetime
import json

@dataclass
class Entity:
    """实体节点"""
    id: str
    name: str
    entity_type: str  # person, project, skill, concept, etc.
    attributes: Dict[str, any]
    created_at: datetime
    updated_at: datetime
    confidence: float  # 提取置信度

@dataclass
class Relation:
    """关系边"""
    id: str
    source_id: str
    target_id: str
    relation_type: str  # knows, works_on, prefers, etc.
    weight: float  # 关系强度
    evidence: str  # 来源证据
    created_at: datetime

class KnowledgeGraph:
    """知识图谱管理器"""
    
    def __init__(self, storage_backend: str = "postgres"):
        self.entities: Dict[str, Entity] = {}
        self.relations: Dict[str, Relation] = {}
        self.entity_index: Dict[str, Set[str]] = {}  # name -> entity_ids
        self.relation_index: Dict[str, Set[str]] = {}  # entity_id -> relation_ids
        
    def add_entity(self, entity: Entity) -> str:
        """添加实体"""
        # 检查是否存在相似实体
        similar = self.find_similar_entities(entity.name, entity.entity_type)
        if similar and similar.confidence > 0.8:
            # 合并属性
            return self._merge_entities(similar, entity)
        
        self.entities[entity.id] = entity
        self._index_entity(entity)
        return entity.id
    
    def add_relation(self, relation: Relation) -> str:
        """添加关系"""
        # 检查是否存在相反关系
        existing = self._find_relation(
            relation.target_id, 
            relation.source_id, 
            relation.relation_type
        )
        if existing:
            # 更新关系权重
            existing.weight = (existing.weight + relation.weight) / 2
            return existing.id
        
        self.relations[relation.id] = relation
        self._index_relation(relation)
        return relation.id
    
    def get_entity_context(self, entity_id: str, depth: int = 2) -> Dict:
        """获取实体上下文（多跳关系）"""
        context = {
            "entity": self.entities.get(entity_id),
            "relations": [],
            "related_entities": []
        }
        
        # BFS 遍历关系
        visited = {entity_id}
        queue = [(entity_id, 0)]
        
        while queue:
            current_id, current_depth = queue.pop(0)
            if current_depth >= depth:
                break
                
            for rel_id in self.relation_index.get(current_id, []):
                rel = self.relations[rel_id]
                context["relations"].append(rel)
                
                # 获取关联实体
                other_id = rel.target_id if rel.source_id == current_id else rel.source_id
                if other_id not in visited:
                    visited.add(other_id)
                    context["related_entities"].append(self.entities[other_id])
                    queue.append((other_id, current_depth + 1))
        
        return context
    
    def find_path(self, source_id: str, target_id: str) -> List[Relation]:
        """查找两个实体之间的路径"""
        # Dijkstra 或 BFS 实现
        pass
```

#### 改进 2：智能记忆提取器

**参考**: supermemory 的实体提取和 Mem0 的提取架构

```python
# server/memory/intelligent_extractor.py

from typing import List, Dict, Tuple, Optional
import re
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

@dataclass
class ExtractionResult:
    """提取结果"""
    entities: List[Dict]  # 提取的实体
    relations: List[Dict]  # 提取的关系
    facts: List[Dict]  # 提取的事实
    confidence: float  # 整体置信度

class IntelligentMemoryExtractor:
    """智能记忆提取器"""
    
    def __init__(self, llm_client=None):
        self.llm_client = llm_client
        self.rule_extractor = RuleBasedExtractor()
        self.entity_patterns = self._load_entity_patterns()
        self.relation_patterns = self._load_relation_patterns()
    
    def extract(self, message: str, context: Dict = None) -> ExtractionResult:
        """多阶段提取"""
        # 阶段 1: 规则快速提取
        rule_results = self.rule_extractor.extract(message)
        
        # 阶段 2: LLM 深度提取（如果启用）
        llm_results = None
        if self.llm_client and self._should_use_llm(message, rule_results):
            llm_results = self._llm_extraction(message, context)
        
        # 阶段 3: 结果融合
        return self._merge_results(rule_results, llm_results)
    
    def _llm_extraction(self, message: str, context: Dict) -> ExtractionResult:
        """LLM 辅助提取"""
        prompt = f"""
分析以下文本，提取实体、关系和事实。

文本: {message}

请以 JSON 格式返回:
{{
  "entities": [
    {{"name": "实体名", "type": "person/project/skill/concept", "attributes": {{}}}}
  ],
  "relations": [
    {{"source": "实体A", "target": "实体B", "relation": "关系类型", "evidence": "原文依据"}}
  ],
  "facts": [
    {{"content": "事实内容", "type": "preference/habit/knowledge", "confidence": 0.9}}
  ]
}}
"""
        response = self.llm_client.generate(prompt)
        return self._parse_llm_response(response)
    
    def _should_use_llm(self, message: str, rule_results: ExtractionResult) -> bool:
        """判断是否需要 LLM 提取"""
        # 规则提取结果不足时使用 LLM
        if len(rule_results.entities) < 2 and len(rule_results.facts) < 1:
            return True
        # 消息包含复杂句式时使用 LLM
        complex_patterns = ['因为', '所以', '虽然', '但是', '如果', '那么']
        if any(p in message for p in complex_patterns):
            return True
        return False


class RuleBasedExtractor:
    """规则提取器（增强版）"""
    
    def __init__(self):
        self.entity_patterns = {
            "person": [
                (r'我叫(\S+)', 'name'),
                (r'我是(\S+?)(?:，|。|！)', 'identity'),
                (r'我的(\S+)是(\S+)', 'attribute'),
            ],
            "project": [
                (r'我在做(\S+?)项目', 'name'),
                (r'我在开发(\S+)', 'name'),
                (r'我的项目(\S+)', 'attribute'),
            ],
            "skill": [
                (r'我会(\S+)', 'name'),
                (r'我精通(\S+)', 'name'),
                (r'我熟悉(\S+)', 'name'),
            ],
        }
        
        self.relation_patterns = {
            "works_on": [
                (r'(\S+)在做(\S+)项目', ('subject', 'object')),
                (r'(\S+)开发(\S+)', ('subject', 'object')),
            ],
            "knows": [
                (r'(\S+)熟悉(\S+)', ('subject', 'object')),
                (r'(\S+)会(\S+)', ('subject', 'object')),
            ],
            "prefers": [
                (r'(\S+)喜欢(\S+)', ('subject', 'object')),
                (r'(\S+)偏好(\S+)', ('subject', 'object')),
            ],
        }
    
    def extract(self, message: str) -> ExtractionResult:
        """规则提取"""
        entities = []
        relations = []
        facts = []
        
        # 提取实体
        for entity_type, patterns in self.entity_patterns.items():
            for pattern, attr_name in patterns:
                matches = re.finditer(pattern, message)
                for match in matches:
                    entities.append({
                        "name": match.group(1),
                        "type": entity_type,
                        "attributes": {attr_name: match.group(2) if len(match.groups()) > 1 else match.group(1)},
                        "confidence": 0.9
                    })
        
        # 提取关系
        for relation_type, patterns in self.relation_patterns.items():
            for pattern, roles in patterns:
                matches = re.finditer(pattern, message)
                for match in matches:
                    relations.append({
                        "source": match.group(1) if roles[0] == 'subject' else match.group(2),
                        "target": match.group(2) if roles[1] == 'object' else match.group(1),
                        "relation": relation_type,
                        "evidence": match.group(0),
                        "confidence": 0.85
                    })
        
        return ExtractionResult(
            entities=entities,
            relations=relations,
            facts=facts,
            confidence=0.9 if entities or relations else 0.0
        )
```

#### 改进 3：短期记忆管理

```python
# server/memory/short_term_memory.py

from typing import List, Dict, Optional
from datetime import datetime, timedelta
from collections import deque
import json

class ShortTermMemory:
    """短期记忆管理器"""
    
    def __init__(self, max_turns: int = 10, decay_rate: float = 0.9):
        self.max_turns = max_turns
        self.decay_rate = decay_rate
        self.conversation_buffer: deque = deque(maxlen=max_turns)
        self.session_start: datetime = datetime.now()
        self.active_entities: Dict[str, float] = {}  # entity_id -> attention_weight
    
    def add_message(self, role: str, content: str, entities: List[str] = None):
        """添加消息"""
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "entities": entities or [],
            "importance": self._calculate_importance(content)
        }
        self.conversation_buffer.append(message)
        
        # 更新活跃实体
        for entity_id in entities or []:
            self._update_entity_attention(entity_id)
    
    def get_context(self, max_tokens: int = 2000) -> str:
        """获取上下文（带衰减）"""
        context_parts = []
        total_tokens = 0
        
        for i, msg in enumerate(reversed(self.conversation_buffer)):
            # 时间衰减
            decay = self.decay_rate ** i
            
            # 重要性加权
            weighted_content = self._weight_content(msg, decay)
            
            # Token 限制
            msg_tokens = len(weighted_content.split())
            if total_tokens + msg_tokens > max_tokens:
                break
            
            context_parts.insert(0, weighted_content)
            total_tokens += msg_tokens
        
        return "\n".join(context_parts)
    
    def get_active_entities(self, threshold: float = 0.3) -> List[str]:
        """获取活跃实体"""
        # 应用衰减
        self._apply_decay()
        
        return [
            entity_id for entity_id, weight in self.active_entities.items()
            if weight > threshold
        ]
    
    def summarize(self) -> Dict:
        """总结短期记忆"""
        return {
            "turns": len(self.conversation_buffer),
            "duration": (datetime.now() - self.session_start).total_seconds(),
            "active_entities": self.get_active_entities(),
            "key_topics": self._extract_topics()
        }
    
    def _calculate_importance(self, content: str) -> float:
        """计算消息重要性"""
        importance_keywords = ['重要', '记住', '别忘了', '关键', '必须', 'important']
        score = sum(0.1 for kw in importance_keywords if kw in content.lower())
        return min(1.0, 0.5 + score)
    
    def _update_entity_attention(self, entity_id: str):
        """更新实体注意力权重"""
        current = self.active_entities.get(entity_id, 0)
        self.active_entities[entity_id] = min(1.0, current + 0.3)
    
    def _apply_decay(self):
        """应用注意力衰减"""
        for entity_id in self.active_entities:
            self.active_entities[entity_id] *= self.decay_rate
```

#### 改进 4：MCP 协议支持

**参考**: supermemory 的 `apps/mcp`

```python
# server/memory/mcp_server.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional, Any
import json

router = APIRouter()

class MCPMemoryResource(BaseModel):
    """MCP 记忆资源"""
    uri: str
    name: str
    description: str
    mimeType: str = "application/json"

class MCPMemoryContent(BaseModel):
    """MCP 记忆内容"""
    uri: str
    mimeType: str
    text: str

class MCPServer:
    """MCP 协议服务器"""
    
    def __init__(self, memory_service):
        self.memory_service = memory_service
        self.resources: Dict[str, MCPMemoryResource] = {}
    
    async def list_resources(self) -> List[MCPMemoryResource]:
        """列出所有记忆资源"""
        return [
            MCPMemoryResource(
                uri=f"memory://entities/{entity.id}",
                name=entity.name,
                description=f"实体: {entity.entity_type}",
                mimeType="application/json"
            )
            for entity in self.memory_service.knowledge_graph.get_all_entities()
        ]
    
    async def read_resource(self, uri: str) -> MCPMemoryContent:
        """读取记忆资源"""
        # 解析 URI
        if uri.startswith("memory://entities/"):
            entity_id = uri.split("/")[-1]
            entity = self.memory_service.knowledge_graph.get_entity(entity_id)
            return MCPMemoryContent(
                uri=uri,
                mimeType="application/json",
                text=json.dumps(entity.to_dict(), ensure_ascii=False)
            )
        elif uri.startswith("memory://context/"):
            query = uri.split("/")[-1]
            context = await self.memory_service.get_context(query)
            return MCPMemoryContent(
                uri=uri,
                mimeType="text/plain",
                text=context
            )
        raise HTTPException(404, f"Resource not found: {uri}")
    
    async def search_memories(self, query: str, limit: int = 10) -> List[Dict]:
        """搜索记忆"""
        return await self.memory_service.search(query, limit)


@router.get("/mcp/resources")
async def list_mcp_resources():
    """MCP: 列出资源"""
    server = get_mcp_server()
    return await server.list_resources()

@router.get("/mcp/resources/{uri:path}")
async def read_mcp_resource(uri: str):
    """MCP: 读取资源"""
    server = get_mcp_server()
    full_uri = f"memory://{uri}"
    return await server.read_resource(full_uri)

@router.post("/mcp/search")
async def mcp_search(query: str, limit: int = 10):
    """MCP: 搜索记忆"""
    server = get_mcp_server()
    return await server.search_memories(query, limit)
```

#### 改进 5：记忆合并与更新

```python
# server/memory/memory_merger.py

from typing import List, Dict, Optional
from datetime import datetime
import difflib

class MemoryMerger:
    """记忆合并器"""
    
    def __init__(self, similarity_threshold: float = 0.85):
        self.similarity_threshold = similarity_threshold
    
    def merge_memories(self, existing: Dict, new: Dict) -> Dict:
        """合并两条记忆"""
        # 判断是否需要合并
        if not self._should_merge(existing, new):
            return new
        
        merged = existing.copy()
        
        # 合并属性
        if "attributes" in new:
            if "attributes" not in merged:
                merged["attributes"] = {}
            merged["attributes"].update(new["attributes"])
        
        # 更新时间戳
        merged["updated_at"] = datetime.now().isoformat()
        
        # 增加置信度
        merged["confidence"] = min(1.0, existing.get("confidence", 0.5) + 0.1)
        
        # 合并证据
        if "evidence" in new:
            if "evidence" not in merged:
                merged["evidence"] = []
            if isinstance(merged["evidence"], str):
                merged["evidence"] = [merged["evidence"]]
            merged["evidence"].append(new["evidence"])
        
        return merged
    
    def detect_contradiction(self, existing: Dict, new: Dict) -> Optional[Dict]:
        """检测矛盾"""
        # 检查属性冲突
        if existing.get("type") != new.get("type"):
            return {
                "type": "type_conflict",
                "existing_type": existing.get("type"),
                "new_type": new.get("type"),
                "resolution": "ask_user"  # 或 "keep_recent", "keep_confident"
            }
        
        # 检查值冲突
        for key in ["name", "value"]:
            if key in existing and key in new:
                if existing[key] != new[key]:
                    return {
                        "type": "value_conflict",
                        "field": key,
                        "existing_value": existing[key],
                        "new_value": new[key],
                        "resolution": "keep_recent"
                    }
        
        return None
    
    def _should_merge(self, existing: Dict, new: Dict) -> bool:
        """判断是否应该合并"""
        # 同一实体
        if existing.get("id") == new.get("id"):
            return True
        
        # 名称相似
        if "name" in existing and "name" in new:
            similarity = difflib.SequenceMatcher(
                None, 
                existing["name"], 
                new["name"]
            ).ratio()
            if similarity > self.similarity_threshold:
                return True
        
        return False


class MemoryUpdater:
    """记忆更新器"""
    
    def __init__(self, knowledge_graph, merger: MemoryMerger):
        self.kg = knowledge_graph
        self.merger = merger
    
    def update_entity(self, entity_id: str, updates: Dict) -> Dict:
        """更新实体"""
        existing = self.kg.get_entity(entity_id)
        if not existing:
            raise ValueError(f"Entity not found: {entity_id}")
        
        # 检测矛盾
        contradiction = self.merger.detect_contradiction(existing, updates)
        if contradiction:
            return self._handle_contradiction(existing, updates, contradiction)
        
        # 合并更新
        merged = self.merger.merge_memories(existing, updates)
        self.kg.update_entity(entity_id, merged)
        
        return merged
    
    def _handle_contradiction(self, existing: Dict, new: Dict, contradiction: Dict) -> Dict:
        """处理矛盾"""
        resolution = contradiction["resolution"]
        
        if resolution == "keep_recent":
            # 保留最新的
            return new
        elif resolution == "keep_confident":
            # 保留置信度高的
            if new.get("confidence", 0) > existing.get("confidence", 0):
                return new
            return existing
        elif resolution == "ask_user":
            # 标记需要用户确认
            return {
                "status": "conflict",
                "existing": existing,
                "new": new,
                "contradiction": contradiction
            }
        
        return new
```

### 3.3 数据库升级方案

**PostgreSQL + pgvector 替代 ChromaDB**

```sql
-- schema.sql

-- 实体表
CREATE TABLE entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    attributes JSONB DEFAULT '{}',
    embedding vector(1536),  -- OpenAI embedding 维度
    confidence FLOAT DEFAULT 0.5,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    user_id VARCHAR(100) DEFAULT 'default'
);

-- 关系表
CREATE TABLE relations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID REFERENCES entities(id) ON DELETE CASCADE,
    target_id UUID REFERENCES entities(id) ON DELETE CASCADE,
    relation_type VARCHAR(100) NOT NULL,
    weight FLOAT DEFAULT 1.0,
    evidence TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(source_id, target_id, relation_type)
);

-- 记忆表
CREATE TABLE memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content TEXT NOT NULL,
    memory_type VARCHAR(50) NOT NULL,
    embedding vector(1536),
    importance FLOAT DEFAULT 0.5,
    access_count INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    last_accessed TIMESTAMP DEFAULT NOW(),
    user_id VARCHAR(100) DEFAULT 'default'
);

-- 向量索引
CREATE INDEX ON entities USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX ON memories USING ivfflat (embedding vector_cosine_ops);

-- 全文索引
CREATE INDEX idx_entities_name ON entities USING gin(to_tsvector('simple', name));
CREATE INDEX idx_memories_content ON memories USING gin(to_tsvector('simple', content));

-- 图查询索引
CREATE INDEX idx_relations_source ON relations(source_id);
CREATE INDEX idx_relations_target ON relations(target_id);
CREATE INDEX idx_relations_type ON relations(relation_type);
```

---

## 四、实施计划

### 阶段 1：基础架构升级（2 周）

| 任务 | 描述 | 优先级 |
|-----|------|-------|
| 1.1 | 部署 PostgreSQL + pgvector | 高 |
| 1.2 | 实现知识图谱基础类 | 高 |
| 1.3 | 迁移现有记忆数据 | 高 |
| 1.4 | 实现短期记忆管理器 | 中 |

### 阶段 2：智能提取增强（2 周）

| 任务 | 描述 | 优先级 |
|-----|------|-------|
| 2.1 | 增强规则提取器 | 高 |
| 2.2 | 实现 LLM 辅助提取 | 高 |
| 2.3 | 实现实体关系提取 | 高 |
| 2.4 | 实现记忆合并器 | 中 |

### 阶段 3：高级功能（2 周）

| 任务 | 描述 | 优先级 |
|-----|------|-------|
| 3.1 | 实现 MCP 协议支持 | 中 |
| 3.2 | 实现多跳关系查询 | 中 |
| 3.3 | 实现记忆遗忘机制 | 低 |
| 3.4 | 实现记忆可视化 API | 低 |

### 阶段 4：集成与测试（1 周）

| 任务 | 描述 | 优先级 |
|-----|------|-------|
| 4.1 | 集成到现有聊天系统 | 高 |
| 4.2 | 编写单元测试 | 高 |
| 4.3 | 性能优化 | 中 |
| 4.4 | 文档更新 | 中 |

---

## 五、预期收益

| 改进项 | 当前状态 | 改进后 | 提升 |
|-------|---------|-------|------|
| 记忆提取准确率 | ~60% (规则) | ~90% (规则+LLM) | +50% |
| 关联推理能力 | 无 | 知识图谱多跳 | 新增 |
| 跨平台同步 | 无 | MCP 协议 | 新增 |
| 记忆去重 | 无 | 智能合并 | 新增 |
| 检索性能 | ChromaDB | PostgreSQL+pgvector | +30% |
| 上下文管理 | 全量 | 三级架构 | 效率+40% |

---

## 六、参考资源

1. **Supermemory GitHub**: https://github.com/supermemoryai/supermemory
2. **Mem0 记忆架构**: 实体关系图谱提取
3. **MCP 协议规范**: Model Context Protocol
4. **pgvector 文档**: PostgreSQL 向量扩展
5. **AI Agent 记忆系统**: 短期/长期记忆架构设计
