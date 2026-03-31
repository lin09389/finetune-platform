# 意图检测系统改进计划 - LLM 优先方案

## 问题分析

### 当前问题

1. **规则匹配太死板** - 依赖硬编码的正则表达式，无法理解语义
2. **BERT 分类器没有对话类别** - 只有操作类意图，导致问候语被错误分类
3. **检测顺序不合理** - 规则匹配优先级太高，容易产生误判
4. **没有智能语义理解** - 无法区分"你好"和"打开你好应用"

### 用户需求

使用 LLM 理解用户意图，实现更智能的意图检测。

## 改进方案

### 核心思路：LLM 优先

将 LLM 作为主要的意图理解引擎，规则匹配和 BERT 作为快速缓存和辅助。

### 检测流程

```
用户输入
    ↓
[1] 快速对话意图检测（规则）
    → 如果是对话意图，直接返回 detected=False
    ↓
[2] LLM 意图理解（主要）
    → 使用 LLM 分析用户意图
    → 返回结构化的意图结果
    ↓
[3] 规则/BERT 辅助验证（可选）
    → 如果 LLM 置信度低，使用规则/BERT 验证
    ↓
返回结果
```

## 实现步骤

### 步骤 1: 创建 LLM 意图理解模块

创建 `server/agent/intent/methods/llm_intent_understanding.py`：

```python
# -*- coding: utf-8 -*-
"""
意图检测方法 - LLM 意图理解

使用大语言模型进行语义级别的意图理解
"""
import logging
from typing import Optional, Dict, Any
import json

from ..models import IntentResult, DetectionMethod, ConfidenceLevel, IntentCategory

logger = logging.getLogger(__name__)

LLM_INTENT_PROMPT = """你是一个智能意图识别助手。请分析用户的输入，理解用户的真实意图。

## 意图分类

### 1. 对话意图 (conversation)
用户想要进行对话、聊天、提问，而不是执行具体操作：
- 问候：你好、hi、hello
- 感谢：谢谢、thanks
- 提问：请问...、我想问...
- 能力询问：你能做什么？
- 闲聊：今天天气怎么样？

### 2. 操作意图 (action)
用户想要执行具体的操作：

#### 文件操作 (file_operation)
- 创建文件：创建一个 test.py 文件
- 读取文件：读取 main.py 的内容
- 修改文件：把 config.json 改成...
- 删除文件：删除 temp.txt

#### 应用控制 (app_control)
- 打开应用：打开微信、启动 VS Code
- 关闭应用：关闭浏览器

#### 浏览器操作 (browser_operation)
- 打开网址：打开 https://google.com

#### 系统操作 (system_operation)
- 截图：截个屏
- 窗口管理：切换窗口

## 分析要求

1. 理解用户输入的语义，不要只看关键词
2. 区分"帮我写代码"（对话）和"帮我打开微信"（操作）
3. 如果不确定，倾向于判断为对话意图

## 返回格式

请以 JSON 格式返回：

```json
{
    "intent_type": "conversation 或 action",
    "action": "具体操作类型（如果是操作意图）",
    "params": {"参数名": "参数值"},
    "confidence": 0.0-1.0,
    "description": "意图描述",
    "reasoning": "判断理由"
}
```

## 用户输入
{user_input}

请直接返回 JSON，不要添加其他内容。"""


class LLMIntentUnderstanding:
    """LLM 意图理解器"""
    
    def __init__(self, llm_client: Optional[Any] = None):
        self._llm_client = llm_client
    
    def set_llm_client(self, client: Any):
        self._llm_client = client
    
    def understand(self, text: str, session_id: Optional[str] = None) -> Optional[IntentResult]:
        """使用 LLM 理解用户意图"""
        if not self._llm_client:
            return None
        
        try:
            prompt = LLM_INTENT_PROMPT.format(user_input=text)
            
            # 调用 LLM
            response = self._call_llm(prompt)
            
            if not response:
                return None
            
            # 解析响应
            return self._parse_response(response, text, session_id)
            
        except Exception as e:
            logger.warning(f"LLM 意图理解失败: {e}")
            return None
    
    def _call_llm(self, prompt: str) -> Optional[str]:
        """调用 LLM"""
        try:
            # 根据不同的 LLM 客户端类型调用
            if hasattr(self._llm_client, 'chat'):
                # OpenAI 风格
                response = self._llm_client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=500
                )
                return response.choices[0].message.content
            elif hasattr(self._llm_client, 'generate'):
                # 本地模型
                return self._llm_client.generate(prompt)
            else:
                logger.warning("未知的 LLM 客户端类型")
                return None
        except Exception as e:
            logger.error(f"LLM 调用失败: {e}")
            return None
    
    def _parse_response(self, response: str, text: str, session_id: Optional[str]) -> IntentResult:
        """解析 LLM 响应"""
        try:
            # 清理响应
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]
            
            result = json.loads(response)
            
            intent_type = result.get("intent_type", "conversation")
            confidence = float(result.get("confidence", 0.8))
            
            # 如果是对话意图，返回 detected=False
            if intent_type == "conversation":
                return IntentResult(
                    detected=False,
                    intent_type="conversation",
                    action=None,
                    params={},
                    description=result.get("description", "对话意图"),
                    confidence=confidence,
                    confidence_level=ConfidenceLevel.from_score(confidence),
                    method=DetectionMethod.LLM,
                    category=IntentCategory.CONVERSATION,
                    need_confirm=False,
                    alternatives=[],
                    raw_match=text,
                    session_id=session_id
                )
            
            # 如果是操作意图，返回 detected=True
            action = result.get("action", "")
            params = result.get("params", {})
            
            return IntentResult(
                detected=True,
                intent_type=action,
                action=action,
                params=params,
                description=result.get("description", ""),
                confidence=confidence,
                confidence_level=ConfidenceLevel.from_score(confidence),
                method=DetectionMethod.LLM,
                category=self._get_category(action),
                need_confirm=False,
                alternatives=[],
                raw_match=text,
                session_id=session_id
            )
            
        except json.JSONDecodeError as e:
            logger.warning(f"LLM 响应解析失败: {e}")
            return None
    
    def _get_category(self, action: str) -> IntentCategory:
        """根据 action 获取类别"""
        if action.startswith("file_"):
            return IntentCategory.FILE_OPERATION
        elif action.startswith("app_"):
            return IntentCategory.APP_CONTROL
        elif action in ["url_open", "browser_open"]:
            return IntentCategory.BROWSER_OPERATION
        elif action in ["screenshot", "mouse_click", "keyboard_type"]:
            return IntentCategory.CUA_OPERATION
        else:
            return IntentCategory.UNKNOWN


llm_intent_understanding = LLMIntentUnderstanding()
```

### 步骤 2: 修改检测器主逻辑

修改 `server/agent/intent/detector.py`：

```python
from .methods.llm_intent_understanding import llm_intent_understanding

class IntentDetector:
    def detect(self, text: str, session_id: Optional[str] = None, context: Optional[Dict[str, Any]] = None) -> IntentResult:
        start_time = time.time()
        
        try:
            text = text.strip()
            if not text:
                return self._create_empty_result(session_id)
            
            # 1. 快速对话意图检测（规则）
            conversation_result = self._quick_conversation_check(text, session_id)
            if conversation_result:
                return conversation_result
            
            # 2. LLM 意图理解（主要方式）
            llm_result = llm_intent_understanding.understand(text, session_id)
            if llm_result:
                if llm_result.confidence >= 0.7:
                    return llm_result
                # 如果 LLM 置信度低，继续使用传统方法验证
            
            # 3. 传统方法作为 fallback
            results = self._run_detection_methods(text, session_id)
            
            if not results:
                return self._create_unknown_result(text, session_id)
            
            best_result = self._select_best_result(results, text, session_id)
            
            # 4. 如果 LLM 有结果，与传统方法结果融合
            if llm_result:
                best_result = self._merge_results(llm_result, best_result)
            
            return best_result
            
        except Exception as e:
            logger.error(f"意图检测失败: {e}")
            return error_handler.create_error_result("detection_failed", text, session_id)
    
    def _quick_conversation_check(self, text: str, session_id: Optional[str]) -> Optional[IntentResult]:
        """快速对话意图检测"""
        import re
        text_lower = text.lower().strip()
        
        # 简单的对话模式
        conversation_patterns = [
            r'^(你好|您好|hi|hello|hey|嗨|哈喽)',
            r'^(谢谢|感谢|多谢|thanks)',
            r'^(再见|拜拜|bye)',
            r'^(你是谁|你叫什么|你能做什么)',
            r'^(好的|明白|收到|ok)$',
        ]
        
        for pattern in conversation_patterns:
            if re.match(pattern, text_lower, re.IGNORECASE):
                return IntentResult(
                    detected=False,
                    intent_type="conversation",
                    action=None,
                    params={},
                    description="对话意图",
                    confidence=1.0,
                    confidence_level=ConfidenceLevel.HIGH,
                    method=DetectionMethod.RULE,
                    category=IntentCategory.CONVERSATION,
                    need_confirm=False,
                    alternatives=[],
                    raw_match=text,
                    session_id=session_id
                )
        
        return None
```

### 步骤 3: 配置 LLM 客户端

在 `server/agent/intent/__init__.py` 中初始化 LLM 客户端：

```python
from .methods.llm_intent_understanding import llm_intent_understanding

def init_llm_client(llm_client):
    """初始化 LLM 客户端"""
    llm_intent_understanding.set_llm_client(llm_client)
```

### 步骤 4: 在 API 中传递 LLM 客户端

修改 `server/api/agent.py`：

```python
from agent.intent import init_llm_client

# 在应用启动时初始化
def get_llm_client():
    """获取 LLM 客户端"""
    # 使用已有的推理客户端
    from core.inference import get_inference_client
    return get_inference_client()

# 初始化意图检测器的 LLM 客户端
init_llm_client(get_llm_client())
```

## 文件修改清单

| 文件 | 修改内容 |
|------|----------|
| `server/agent/intent/methods/llm_intent_understanding.py` | 新建 - LLM 意图理解模块 |
| `server/agent/intent/detector.py` | 修改检测流程，LLM 优先 |
| `server/agent/intent/__init__.py` | 添加 LLM 客户端初始化 |
| `server/api/agent.py` | 传递 LLM 客户端 |

## 测试用例

| 输入 | 期望结果 | LLM 理解 |
|------|----------|----------|
| "你好" | detected=False | 对话意图 - 问候 |
| "谢谢" | detected=False | 对话意图 - 感谢 |
| "你能做什么" | detected=False | 对话意图 - 能力询问 |
| "帮我写一个函数" | detected=False | 对话意图 - 编程帮助 |
| "打开微信" | detected=True, app_open | 操作意图 - 应用控制 |
| "读取 test.txt" | detected=True, file_read | 操作意图 - 文件操作 |
| "帮我打开微信" | detected=True, app_open | 操作意图 - 应用控制 |

## 优势

1. **语义理解** - LLM 能真正理解用户意图，而非依赖关键词匹配
2. **灵活性** - 无需维护大量规则，LLM 能处理各种表达方式
3. **可扩展** - 新增意图类型只需更新 prompt
4. **智能判断** - 能区分"帮我写代码"和"帮我打开应用"

## 风险评估

- **性能** - LLM 调用有延迟，需要缓存优化
- **成本** - 需要调用 LLM API（如果使用云端）
- **可靠性** - LLM 输出可能不稳定，需要解析容错

## 缓解措施

1. **快速对话检测** - 简单问候语直接返回，不调用 LLM
2. **本地模型** - 使用本地部署的小模型（如 Qwen-1.8B）
3. **结果缓存** - 相似输入复用结果
4. **Fallback** - LLM 失败时使用传统方法
