# 意图检测模块重构计划

## 一、问题诊断

### 1.1 当前架构问题

| 问题类型 | 具体表现 | 影响 |
|---------|---------|------|
| **重复检测器** | 4个独立检测器实现 | 维护困难、行为不一致 |
| **重复数据模型** | IntentResult 在3个文件中定义 | 类型混乱、转换成本高 |
| **重复枚举** | DetectionMethod 在4个文件中定义 | 导入混乱、扩展困难 |
| **重复规则** | 60+条规则在3个文件中重复 | 更新遗漏、行为不一致 |
| **文件依赖混乱** | 循环依赖、导入路径不统一 | 难以理解、测试困难 |

### 1.2 当前文件结构

```
server/agent/intent/
├── detector.py (800行)           # EnhancedIntentDetector
├── smart_detector.py (650行)     # SmartIntentDetector  
├── unified_detector.py (550行)   # UnifiedIntentDetector
├── models.py (177行)             # 数据模型
├── semantic_matcher.py           # 语义匹配
├── bert_classifier.py            # BERT分类
├── confidence.py                 # 置信度
├── context_aware.py              # 上下文感知
├── metrics.py                    # 性能指标
└── ...

server/core/
└── intent_detector.py (60行)     # 又一个检测器
```

---

## 二、目标架构

### 2.1 新目录结构

```
server/agent/intent/
├── __init__.py                    # 统一导出入口
├── detector.py                    # 统一检测器（唯一入口）
├── models.py                      # 统一数据模型
│
├── core/                          # 核心组件
│   ├── __init__.py
│   ├── patterns.py                # 统一规则模式库
│   ├── param_extractor.py         # 统一参数提取器
│   ├── confidence.py              # 统一置信度计算
│   └── context.py                 # 统一上下文管理
│
├── methods/                       # 检测方法
│   ├── __init__.py
│   ├── rule_matcher.py            # 规则匹配器
│   ├── semantic_matcher.py        # 语义匹配器（保留优化）
│   ├── bert_classifier.py         # BERT分类器（保留优化）
│   └── llm_detector.py            # LLM检测器
│
├── handlers/                      # 处理器
│   ├── __init__.py
│   ├── clarification.py           # 澄清对话处理
│   ├── error_handler.py           # 错误处理
│   └── metrics.py                 # 性能指标
│
└── _deprecated/                   # 待删除文件
    ├── smart_detector.py
    ├── enhanced_detector.py
    └── unified_detector.py
```

### 2.2 统一数据模型

```python
# models.py

class DetectionMethod(str, Enum):
    RULE = "rule"
    SEMANTIC = "semantic"
    BERT = "bert"
    LLM = "llm"
    CONTEXT = "context"

class ConfidenceLevel(str, Enum):
    HIGH = "high"      # >= 0.85
    MEDIUM = "medium"  # >= 0.65
    LOW = "low"        # >= 0.45

class IntentCategory(str, Enum):
    FILE_OPERATION = "file_operation"
    APP_CONTROL = "app_control"
    BROWSER_OPERATION = "browser_operation"
    CUA_OPERATION = "cua_operation"
    SYSTEM_OPERATION = "system_operation"

@dataclass
class IntentResult:
    detected: bool
    intent_type: str
    action: str
    params: Dict[str, Any]
    confidence: float
    confidence_level: ConfidenceLevel
    method: DetectionMethod
    category: IntentCategory
    need_confirm: bool
    alternatives: List[Tuple[str, float]]
```

### 2.3 统一检测流程

```
用户输入
    │
    ▼
┌─────────────────────────────────────────┐
│          IntentDetector.detect()         │
├─────────────────────────────────────────┤
│  1. ContextManager.get_context()         │
│  2. RuleMatcher.match()      ──┐         │
│  3. BERTClassifier.classify() ─┼── 并行  │
│  4. SemanticMatcher.match()  ──┘         │
│  5. ResultMerger.merge()                 │
│  6. ConfidenceCalculator.calculate()     │
│  7. ContextReferenceResolver.resolve()   │
│  8. ClarificationHandler.handle()        │
└─────────────────────────────────────────┘
    │
    ▼
IntentResult
```

---

## 三、实施步骤

### Phase 1: 创建核心组件

#### Step 1.1: 重写统一数据模型
- 文件: `server/agent/intent/models.py`
- 内容:
  - 合并所有枚举定义（DetectionMethod, ConfidenceLevel, IntentCategory）
  - 统一 IntentResult 数据类
  - 统一 MultiIntentResult 数据类
  - 统一 DetectionMetrics 数据类
  - 统一 ConversationContext 数据类

#### Step 1.2: 创建统一规则模式库
- 文件: `server/agent/intent/core/patterns.py`
- 内容:
  - 合并所有规则模式（60+条）
  - 按类别组织（FILE, APP, BROWSER, CUA, SYSTEM）
  - 支持优先级排序
  - 支持危险操作标记

#### Step 1.3: 创建统一参数提取器
- 文件: `server/agent/intent/core/param_extractor.py`
- 内容:
  - 合并 ParameterExtractor, SmartParamExtractor
  - 统一提取方法（path, url, number, date, content）
  - 支持类型推断

#### Step 1.4: 创建统一置信度计算器
- 文件: `server/agent/intent/core/confidence.py`
- 内容:
  - 统一置信度计算逻辑
  - 支持多因素加权
  - 支持上下文加成

#### Step 1.5: 创建统一上下文管理器
- 文件: `server/agent/intent/core/context.py`
- 内容:
  - 合并 ConversationContext 实现
  - 统一会话管理
  - 统一引用解析

### Phase 2: 重构检测方法

#### Step 2.1: 重构规则匹配器
- 文件: `server/agent/intent/methods/rule_matcher.py`
- 内容:
  - 使用统一规则模式库
  - 使用统一参数提取器
  - 返回统一 IntentResult

#### Step 2.2: 优化语义匹配器
- 文件: `server/agent/intent/methods/semantic_matcher.py`
- 内容:
  - 保留现有实现
  - 适配统一数据模型
  - 添加接口标准化

#### Step 2.3: 优化BERT分类器
- 文件: `server/agent/intent/methods/bert_classifier.py`
- 内容:
  - 保留现有实现
  - 适配统一数据模型
  - 添加接口标准化

#### Step 2.4: 创建LLM检测器
- 文件: `server/agent/intent/methods/llm_detector.py`
- 内容:
  - 合并各文件中的LLM检测逻辑
  - 统一Prompt模板
  - 统一响应解析

### Phase 3: 重构处理器

#### Step 3.1: 创建澄清对话处理器
- 文件: `server/agent/intent/handlers/clarification.py`
- 内容:
  - 合并 IntentClarifier 实现
  - 统一澄清对话模板
  - 统一响应处理

#### Step 3.2: 创建错误处理器
- 文件: `server/agent/intent/handlers/error_handler.py`
- 内容:
  - 合并 IntelligentErrorHandler 实现
  - 统一错误消息模板
  - 统一建议生成

#### Step 3.3: 优化性能指标
- 文件: `server/agent/intent/handlers/metrics.py`
- 内容:
  - 保留现有实现
  - 适配统一数据模型

### Phase 4: 重写统一检测器

#### Step 4.1: 重写检测器入口
- 文件: `server/agent/intent/detector.py`
- 内容:
  - 创建 IntentDetector 类
  - 实现统一检测流程
  - 支持并行检测
  - 支持LLM Fallback

#### Step 4.2: 创建统一导出
- 文件: `server/agent/intent/__init__.py`
- 内容:
  ```python
  from .detector import IntentDetector, create_detector
  from .models import (
      IntentResult, MultiIntentResult,
      DetectionMethod, ConfidenceLevel, IntentCategory
  )
  
  # 兼容性别名
  UnifiedIntentDetector = IntentDetector
  
  __all__ = [
      'IntentDetector', 'create_detector',
      'IntentResult', 'MultiIntentResult',
      'DetectionMethod', 'ConfidenceLevel', 'IntentCategory',
      'UnifiedIntentDetector'
  ]
  ```

### Phase 5: 清理与迁移

#### Step 5.1: 移动旧文件到 _deprecated
- 移动: `smart_detector.py` → `_deprecated/`
- 移动: `enhanced_detector.py` → `_deprecated/`
- 移动: `unified_detector.py` → `_deprecated/`
- 移动: `core/intent_detector.py` → `_deprecated/`

#### Step 5.2: 更新外部依赖
- 更新: `server/agent/__init__.py`
- 更新: `server/api/agent.py`
- 更新: 所有导入语句

#### Step 5.3: 添加单元测试
- 文件: `server/agent/intent/tests/test_detector.py`
- 内容:
  - 测试统一检测流程
  - 测试各检测方法
  - 测试参数提取
  - 测试置信度计算

---

## 四、预期效果

### 4.1 代码量对比

| 指标 | 重构前 | 重构后 | 减少 |
|------|--------|--------|------|
| 检测器文件数 | 4 | 1 | 75% |
| 总代码行数 | ~2500 | ~1200 | 52% |
| 重复枚举定义 | 4处 | 1处 | 75% |
| 重复规则定义 | 60+条 | 60条（统一） | 消除重复 |

### 4.2 架构优势

| 方面 | 改进 |
|------|------|
| **可维护性** | 单一入口、统一模型、清晰分层 |
| **可扩展性** | 插件式检测方法、易于添加新规则 |
| **一致性** | 统一置信度计算、统一错误处理 |
| **可测试性** | 模块化设计、依赖注入 |

### 4.3 API兼容性

```python
# 旧API（保持兼容）
from agent.intent import UnifiedIntentDetector
detector = UnifiedIntentDetector()
result = detector.detect("创建文件 test.py")

# 新API（推荐）
from agent.intent import IntentDetector
detector = IntentDetector()
result = detector.detect("创建文件 test.py")
```

---

## 五、风险控制

### 5.1 回滚策略
- 保留 `_deprecated/` 目录中的旧文件
- 使用 Git 分支管理
- 灰度发布（5% → 20% → 50% → 100%）

### 5.2 测试策略
- 单元测试覆盖率 > 80%
- 集成测试验证API兼容性
- 性能基准测试（延迟 < 150ms）

### 5.3 监控策略
- 检测成功率监控
- 响应延迟监控
- 错误日志告警

---

## 六、时间表

| 阶段 | 时间 | 任务 |
|------|------|------|
| Phase 1 | Day 1 | 创建核心组件（models, patterns, param_extractor, confidence, context） |
| Phase 2 | Day 2 上午 | 重构检测方法（rule_matcher, semantic_matcher, bert_classifier, llm_detector） |
| Phase 3 | Day 2 下午 | 重构处理器（clarification, error_handler, metrics） |
| Phase 4 | Day 3 上午 | 重写统一检测器（detector.py, __init__.py） |
| Phase 5 | Day 3 下午 | 清理与迁移（_deprecated, 更新依赖, 测试） |

---

## 七、执行确认

执行后将：

1. 创建新的目录结构和文件
2. 合并所有重复代码
3. 移动旧文件到 `_deprecated/` 目录
4. 更新所有外部依赖
5. 添加单元测试
