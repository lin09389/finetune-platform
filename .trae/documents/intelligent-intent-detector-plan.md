# 智能化意图检测器升级计划

## 一、目标

将现有的基于正则表达式的意图检测器升级为更加智能化的检测系统，提升以下能力：
- 模糊指令识别率
- 参数提取准确率
- 上下文理解能力
- 自学习能力

## 二、现有问题分析

### 2.1 当前架构局限

| 问题 | 影响 | 严重程度 |
|------|------|---------|
| 正则表达式过于严格 | 无法识别口语化表达 | 高 |
| 参数提取依赖固定模式 | 提取不准确 | 高 |
| 无学习能力 | 无法适应新表达 | 中 |
| 缺少语义理解 | 无法处理同义词变体 | 中 |

### 2.2 测试失败案例

```
输入: "创建一个test.py文件"
期望: file_path = "test.py"
实际: file_path = "test.py" ✅ (已修复)

输入: "帮我把那个文件弄一下"
期望: 识别为文件操作 + 询问具体操作
实际: 未检测到意图 ❌
```

## 三、升级方案

### 方案 A：规则 + 语义匹配混合架构（推荐）

```
用户消息
    ↓
┌─────────────────────────────────────────┐
│  第一层：快速规则匹配                    │
│  - 正则表达式模式库                      │
│  - 关键词匹配                            │
│  - 置信度 >= 0.8 → 直接返回              │
└─────────────────────────────────────────┘
    ↓ (置信度 < 0.8)
┌─────────────────────────────────────────┐
│  第二层：语义相似度匹配                  │
│  - 预计算意图嵌入向量                    │
│  - 计算消息与意图的相似度               │
│  - 置信度 >= 0.7 → 返回结果              │
└─────────────────────────────────────────┘
    ↓ (置信度 < 0.7)
┌─────────────────────────────────────────┐
│  第三层：LLM 智能后备                    │
│  - 调用本地/云端 LLM                     │
│  - 结构化输出意图和参数                  │
│  - 返回最终结果                          │
└─────────────────────────────────────────┘
```

**优点**：
- 快速响应（规则匹配 < 1ms）
- 准确率高（多层检测）
- 可扩展（易于添加新规则）

**缺点**：
- 实现复杂度中等
- 需要维护嵌入向量

### 方案 B：纯 LLM 驱动架构

```
用户消息 → LLM → 结构化意图输出
```

**优点**：
- 最智能
- 无需维护规则

**缺点**：
- 响应慢（100-500ms）
- 依赖 LLM 可用性
- 成本较高

## 四、实施计划

### 阶段一：增强规则匹配（1-2天）

#### 1.1 优化正则表达式库

**文件**：`server/agent/intent/enhanced_detector.py`

**改进内容**：
1. 添加更多口语化模式
2. 改进参数提取正则
3. 添加否定模式（排除误匹配）

```python
# 新增口语化模式
PATTERNS = [
    {
        "action": ActionType.FILE_CREATE,
        "patterns": [
            r"(?:创建|新建|生成|建立|弄|搞|写|做)",
            r"帮我.*文件",
            r"要一个.*文件",
        ],
        "param_extractors": {
            "file_path": [
                r"([a-zA-Z][\w\-./]*\.[a-zA-Z]{1,10})",  # 标准文件名
                r"叫[它]?([a-zA-Z][\w\-./]*)",  # "叫它test"
            ]
        },
        "negative_patterns": [  # 排除模式
            r"不要.*创建",
            r"删除.*创建",
        ]
    },
]
```

#### 1.2 添加意图分类器

**新文件**：`server/agent/intent/classifier.py`

```python
class IntentClassifier:
    """意图分类器 - 基于关键词和规则"""
    
    def classify(self, message: str) -> List[Tuple[ActionType, float]]:
        """返回候选意图列表及其置信度"""
        scores = {}
        
        # 关键词匹配
        for action, keywords in self.ACTION_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in message) / len(keywords)
            if score > 0:
                scores[action] = score * 0.5
        
        # 规则匹配
        for pattern_def in self.PATTERNS:
            for pattern in pattern_def["patterns"]:
                if re.search(pattern, message):
                    scores[pattern_def["action"]] = max(
                        scores.get(pattern_def["action"], 0),
                        0.7
                    )
        
        return sorted(scores.items(), key=lambda x: x[1], reverse=True)
```

### 阶段二：添加语义匹配（2-3天）

#### 2.1 创建意图嵌入索引

**新文件**：`server/agent/intent/semantic_index.py`

```python
class IntentSemanticIndex:
    """意图语义索引"""
    
    INTENT_EXAMPLES = {
        "file_create": [
            "创建一个新文件",
            "新建文件",
            "生成一个文档",
            "弄一个文件",
            "帮我建个文件",
        ],
        "file_read": [
            "读取文件内容",
            "查看文件",
            "打开文件看看",
            "显示文件内容",
        ],
        # ... 其他意图
    }
    
    def __init__(self, embedder):
        self.embedder = embedder
        self.intent_embeddings = {}
        self._build_index()
    
    def _build_index(self):
        """构建意图嵌入索引"""
        for intent, examples in self.INTENT_EXAMPLES.items():
            embeddings = [self.embedder.embed(ex) for ex in examples]
            self.intent_embeddings[intent] = np.mean(embeddings, axis=0)
    
    def find_similar(self, message: str, top_k: int = 3) -> List[Tuple[str, float]]:
        """查找相似意图"""
        msg_embedding = self.embedder.embed(message)
        similarities = []
        
        for intent, intent_emb in self.intent_embeddings.items():
            sim = cosine_similarity([msg_embedding], [intent_emb])[0][0]
            similarities.append((intent, sim))
        
        return sorted(similarities, key=lambda x: x[1], reverse=True)[:top_k]
```

#### 2.2 集成到检测流程

```python
class EnhancedIntentDetector:
    def detect(self, message: str, context: Optional[Dict] = None) -> EnhancedIntentResult:
        # 第一层：规则匹配
        rule_result = self._rule_detect(message)
        if rule_result and rule_result.confidence >= 0.8:
            return rule_result
        
        # 第二层：语义匹配
        semantic_result = self._semantic_detect(message)
        if semantic_result and semantic_result.confidence >= 0.7:
            return semantic_result
        
        # 第三层：LLM 后备
        if self.llm_detector:
            return await self._llm_detect(message, context)
        
        return EnhancedIntentResult(detected=False)
```

### 阶段三：添加自学习能力（3-5天）

#### 3.1 用户反馈收集

**新文件**：`server/agent/intent/feedback.py`

```python
class IntentFeedbackCollector:
    """意图反馈收集器"""
    
    def record_feedback(
        self,
        message: str,
        detected_intent: str,
        user_action: str,  # "confirm", "reject", "correct"
        correct_intent: Optional[str] = None
    ):
        """记录用户反馈"""
        feedback = {
            "message": message,
            "detected_intent": detected_intent,
            "user_action": user_action,
            "correct_intent": correct_intent,
            "timestamp": datetime.now().isoformat()
        }
        self.feedback_store.append(feedback)
        
        # 如果反馈量大，触发学习
        if len(self.feedback_store) >= 100:
            self._learn_from_feedback()
    
    def _learn_from_feedback(self):
        """从反馈中学习"""
        # 分析错误模式
        # 更新规则权重
        # 添加新的训练样本
        pass
```

#### 3.2 动态规则更新

```python
class DynamicRuleManager:
    """动态规则管理器"""
    
    def add_rule_from_feedback(self, message: str, correct_intent: str):
        """从反馈中提取新规则"""
        # 提取关键词
        keywords = self._extract_keywords(message)
        
        # 生成新规则
        new_rule = {
            "action": correct_intent,
            "patterns": [self._generate_pattern(message, keywords)],
            "source": "feedback",
            "confidence": 0.6
        }
        
        # 添加到规则库
        self.rules.append(new_rule)
```

## 五、预期效果

### 5.1 性能指标

| 指标 | 当前值 | 目标值 |
|------|-------|-------|
| 标准指令识别率 | 85% | 95% |
| 口语化指令识别率 | 60% | 85% |
| 参数提取准确率 | 70% | 90% |
| 平均响应时间 | 50ms | < 100ms |

### 5.2 测试用例

```python
test_cases = [
    ("创建一个test.py文件", "file_create", {"file_path": "test.py"}),
    ("弄一个新文件", "file_create", {}),  # 需要询问文件名
    ("帮我把那个文件弄一下", "file_operation", {}),  # 需要澄清
    ("保存到桌面", "file_write", {"is_desktop": True}),
    ("往里面写点东西", "file_write", {}),  # 需要上下文
    ("第一个文件", "file_read", {}),  # 需要上下文
]
```

## 六、实施优先级

| 任务 | 优先级 | 预计时间 |
|------|-------|---------|
| 优化正则表达式库 | P0 | 1天 |
| 添加意图分类器 | P0 | 1天 |
| 创建语义匹配索引 | P1 | 2天 |
| 集成多层检测流程 | P1 | 1天 |
| 添加反馈收集 | P2 | 2天 |
| 实现自学习 | P2 | 3天 |

## 七、风险与缓解

| 风险 | 可能性 | 缓解措施 |
|------|-------|---------|
| 语义匹配增加延迟 | 中 | 使用预计算嵌入 |
| 规则冲突 | 低 | 添加优先级排序 |
| LLM 不可用 | 中 | 保留规则作为后备 |
