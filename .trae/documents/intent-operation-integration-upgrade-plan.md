# 意图检测模块与本地操作模块融合架构改进升级计划

## 一、改进目标

基于技术评估报告，本次升级旨在解决以下核心问题：
1. BERT 分类器不提取参数，导致意图检测与参数提取分离
2. 多版本检测器并存，维护成本高
3. 参数命名不一致，执行器需兼容多种命名
4. 操作类型扩展存在硬编码问题
5. 会话上下文缺少持久化机制

## 二、改进阶段规划

### 阶段一：基础规范化（优先级：高）

#### 1.1 统一检测器版本
**目标**：移除冗余检测器，统一使用 `UnifiedIntentDetector`

**修改文件**：
- `server/api/agent.py` - 移除旧版检测器实例化和引用
- `server/agent/intent/__init__.py` - 更新导出接口

**具体步骤**：
1. 移除 `_intent_detector`、`_enhanced_detector`、`_smart_detector` 全局变量
2. 移除 `get_intent_detector()`、`get_enhanced_detector()`、`get_smart_detector()` 函数
3. 更新 `/detect-intent`、`/detect-intent-enhanced` 端点，内部调用 `get_unified_detector()`
4. 更新 `/chat-execute` 端点，使用 `UnifiedIntentDetector`

#### 1.2 统一参数命名规范
**目标**：建立统一的参数命名规范，消除歧义

**参数命名规范**：
```
文件操作：
- file_path: 文件路径（统一使用此命名）
- content: 文件内容
- mode: 写入模式

应用操作：
- app_name: 应用名称
- args: 启动参数

系统操作：
- pid: 进程ID
- service_name: 服务名称

CUA操作：
- x, y: 坐标
- button: 鼠标按钮
- text: 输入文本
```

**修改文件**：
- `server/agent/executor.py` - 更新参数获取逻辑
- `server/agent/intent/unified_detector.py` - 更新规则模式中的参数命名
- `server/agent/core/engine/executor.py` - 添加参数兼容层

---

### 阶段二：BERT 参数提取扩展（优先级：高）

#### 2.1 扩展 BERT 模型支持参数抽取
**目标**：让 BERT 分类器能够同时输出意图类型和参数

**技术方案**：
采用序列标注（Sequence Labeling）方法，在 BERT 输出层添加 CRF/softmax 层用于参数抽取

**修改文件**：
- `server/agent/intent/bert_classifier.py` - 扩展模型架构
- `server/agent/intent/train_bert.py` - 更新训练脚本
- `server/agent/intent/training_data_expanded.py` - 添加参数标注数据

**具体步骤**：
1. 定义参数标签体系（BIO 标注）
   - B-FILE_PATH, I-FILE_PATH
   - B-APP_NAME, I-APP_NAME
   - B-URL, I-URL
   - B-CONTENT, I-CONTENT
   - O (非参数)

2. 扩展模型架构
   ```python
   class BERTIntentClassifier:
       def __init__(self):
           self.intent_classifier = nn.Linear(hidden_size, num_intents)
           self.param_tagger = nn.Linear(hidden_size, num_param_tags)
   ```

3. 更新训练数据格式
   ```python
   {
       "text": "创建一个test.py文件",
       "intent": "file_create",
       "params": [
           {"text": "test.py", "type": "file_path", "start": 4, "end": 11}
       ]
   }
   ```

4. 修改预测接口
   ```python
   def predict(self, text: str) -> Tuple[str, float, Dict[str, Any]]:
       # 返回 (意图类型, 置信度, 参数字典)
   ```

#### 2.2 更新 UnifiedIntentDetector 集成
**修改文件**：
- `server/agent/intent/unified_detector.py`

**具体步骤**：
1. 修改 `_init_components()` 方法，使用新的 BERT 接口
2. 更新 `detect()` 方法，优先使用 BERT 提取的参数
3. 添加参数合并逻辑（BERT 参数 + 规则参数）

---

### 阶段三：操作注册机制重构（优先级：中）

#### 3.1 实现操作注册模式
**目标**：将硬编码的 action_map 改为动态注册机制

**新增文件**：
- `server/agent/core/registry/action_registry.py`

**修改文件**：
- `server/agent/executor.py`
- `server/agent/core/engine/executor.py`

**具体实现**：

```python
# server/agent/core/registry/action_registry.py
class ActionRegistry:
    def __init__(self):
        self._handlers: Dict[str, ActionHandler] = {}
        self._metadata: Dict[str, ActionMetadata] = {}
    
    def register(self, action: str, handler: Callable, metadata: ActionMetadata):
        self._handlers[action] = handler
        self._metadata[action] = metadata
    
    def get_handler(self, action: str) -> Optional[Callable]:
        return self._handlers.get(action)
    
    def get_metadata(self, action: str) -> Optional[ActionMetadata]:
        return self._metadata.get(action)
    
    def list_actions(self) -> List[str]:
        return list(self._handlers.keys())

# 装饰器方式注册
def action_handler(action: str, metadata: ActionMetadata):
    def decorator(func):
        get_action_registry().register(action, func, metadata)
        return func
    return decorator
```

#### 3.2 迁移现有操作
**具体步骤**：
1. 创建 `ActionMetadata` 数据类，定义操作元信息
2. 将 `_file_create`、`_file_read` 等方法改为使用装饰器注册
3. 更新 `AgentExecutor` 使用 `ActionRegistry` 获取处理器

---

### 阶段四：会话持久化（优先级：中）

#### 4.1 实现会话存储接口
**目标**：支持会话上下文的持久化存储

**新增文件**：
- `server/agent/intent/session_store.py`

**技术选型**：
- 方案A：Redis（推荐，支持分布式）
- 方案B：SQLite（轻量级，单机部署）

**具体实现**：

```python
# server/agent/intent/session_store.py
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
import json

class SessionStore(ABC):
    @abstractmethod
    def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        pass
    
    @abstractmethod
    def set(self, session_id: str, data: Dict[str, Any], ttl: int = 3600):
        pass
    
    @abstractmethod
    def delete(self, session_id: str):
        pass

class RedisSessionStore(SessionStore):
    def __init__(self, redis_client):
        self.redis = redis_client
        self.prefix = "intent_session:"
    
    def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        data = self.redis.get(f"{self.prefix}{session_id}")
        return json.loads(data) if data else None
    
    def set(self, session_id: str, data: Dict[str, Any], ttl: int = 3600):
        self.redis.setex(
            f"{self.prefix}{session_id}",
            ttl,
            json.dumps(data, ensure_ascii=False)
        )

class MemorySessionStore(SessionStore):
    """内存存储（默认实现，用于开发环境）"""
    def __init__(self):
        self._store: Dict[str, Dict[str, Any]] = {}
```

#### 4.2 集成到 UnifiedIntentDetector
**修改文件**：
- `server/agent/intent/unified_detector.py`

**具体步骤**：
1. 添加 `session_store` 参数到构造函数
2. 修改 `_get_session_context()` 方法，从存储加载会话
3. 修改会话更新逻辑，同步写入存储

---

### 阶段五：监控与可观测性增强（优先级：低）

#### 5.1 完善性能指标
**修改文件**：
- `server/agent/intent/metrics.py`
- `server/agent/intent/monitoring.py`

**新增指标**：
- 意图检测各阶段耗时分布
- 参数提取成功率
- 会话上下文命中率
- 操作执行成功率按类型分布

#### 5.2 添加分布式追踪
**新增文件**：
- `server/agent/tracing.py`

**集成方案**：
- 使用 OpenTelemetry 标准
- 追踪完整请求链路：API → 意图检测 → 安全评估 → 执行 → 返回

---

## 三、实施时间表

| 阶段 | 任务 | 预计工时 | 依赖 |
|------|------|----------|------|
| 阶段一 | 统一检测器版本 | 4h | 无 |
| 阶段一 | 统一参数命名 | 6h | 无 |
| 阶段二 | BERT 参数提取扩展 | 16h | 阶段一完成 |
| 阶段三 | 操作注册机制 | 8h | 无 |
| 阶段四 | 会话持久化 | 8h | 无 |
| 阶段五 | 监控增强 | 8h | 阶段一-四完成 |

**总计：约 50 工时**

---

## 四、风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| BERT 模型重新训练可能影响现有准确率 | 高 | 保留旧模型作为后备，A/B 测试验证 |
| 参数命名变更可能影响现有 API 调用 | 中 | 添加兼容层，渐进式迁移 |
| Redis 依赖增加部署复杂度 | 低 | 提供内存存储作为默认实现 |

---

## 五、验收标准

### 阶段一验收标准
- [x] 所有 API 端点统一使用 `UnifiedIntentDetector`
- [x] 参数命名一致性测试通过
- [x] 现有功能回归测试通过

### 阶段二验收标准
- [x] BERT 模型支持参数抽取
- [x] 参数提取准确率 >= 85%（待训练验证）
- [x] 意图检测准确率保持 >= 90%（待训练验证）

### 阶段三验收标准
- [x] 操作注册机制可用
- [x] 新增操作无需修改核心代码
- [x] 动态加载/卸载操作支持

### 阶段四验收标准
- [x] 会话持久化功能可用
- [x] 服务重启后会话恢复正常
- [x] 会话 TTL 自动过期

### 阶段五验收标准
- [x] 性能指标完整
- [x] 分布式追踪可用
- [x] 监控面板展示正常

---

## 六、后续优化方向

1. **在线学习**：根据用户反馈持续优化意图检测模型
2. **意图推荐**：基于用户历史行为推荐可能的操作
3. **自然语言理解增强**：支持更复杂的语义理解和推理
4. **跨会话记忆**：支持长期记忆和用户偏好学习
