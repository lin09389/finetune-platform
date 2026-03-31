# AI对话页面本地操作功能改进方案

## 问题诊断

通过分析代码，发现以下核心问题导致本地操作无法实现或伪实现：

### 1. 意图检测问题

#### 1.1 规则匹配覆盖不足
- **位置**: `server/agent/intent/unified_detector.py` 第 350-944 行
- **问题**: 当前依赖正则表达式匹配，规则有限且无法处理复杂/模糊的自然语言请求
- **示例**: 用户说"帮我把刚才生成的代码保存一下"，意图检测器无法正确识别

#### 1.2 参数提取不完整
- **位置**: `server/agent/intent.py` 第 188-293 行
- **问题**: 参数提取依赖正则捕获组，无法处理：
  - 隐式参数（如"保存它"中的"它"）
  - 多步骤操作的参数传递
  - 上下文相关的参数推断

#### 1.3 CUA操作意图检测但未执行
- **位置**: `server/agent/intent/unified_detector.py` 第 693-916 行
- **问题**: 意图检测器支持截图、鼠标点击、键盘输入等操作，但执行器没有对应实现

### 2. 执行器问题

#### 2.1 操作类型不完整
- **位置**: `server/agent/executor.py` 第 116-124 行
- **问题**: 执行器只支持 7 种操作，但意图检测器支持 20+ 种操作
```python
action_map = {
    ActionType.FILE_CREATE: self._file_create,
    ActionType.FILE_READ: self._file_read,
    ActionType.FILE_WRITE: self._file_write,
    ActionType.FILE_DELETE: self._file_delete,
    ActionType.FILE_LIST: self._file_list,
    ActionType.APP_OPEN: self._app_open,
    ActionType.URL_OPEN: self._url_open,
}
# 缺少: SCREENSHOT, MOUSE_CLICK, MOUSE_MOVE, KEYBOARD_TYPE 等
```

#### 2.2 应用白名单限制
- **位置**: `server/agent/security_old.py` (被 executor 引用)
- **问题**: 应用打开有白名单限制，用户请求的应用可能不在列表中

#### 2.3 缺少操作确认和反馈机制
- **问题**: 执行失败时没有智能建议或重试机制

### 3. 前端问题

#### 3.1 Agent执行流程问题
- **位置**: `client/src/pages/Chat.tsx` 第 493-533 行
- **问题**: 
  - `executeAgent` 先于 AI 对话执行，可能打断正常对话流程
  - 执行结果格式化简单，无法展示复杂结果

#### 3.2 错误处理不完善
- **位置**: `client/src/pages/Chat.tsx` 第 1145-1182 行
- **问题**: `formatAgentResult` 只显示简单的成功/失败消息，缺少：
  - 失败原因的详细解释
  - 解决建议
  - 重试选项

### 4. 架构问题

#### 4.1 意图检测与执行分离
- **问题**: 意图检测返回的 `action` 可能不在执行器的 `ActionType` 枚举中
- **位置**: `server/agent/config.py` vs `server/agent/intent/unified_detector.py`

#### 4.2 缺少 LLM 辅助决策
- **问题**: 虽然有 `detect_with_llm` 方法，但默认未启用
- **位置**: `server/agent/intent/unified_detector.py` 第 1581-1614 行

---

## 改进方案

### 第一阶段：修复核心问题（高优先级）

#### 1.1 扩展执行器操作类型

**文件**: `server/agent/executor.py`

需要添加以下操作实现：
- `SCREENSHOT`: 屏幕截图
- `MOUSE_CLICK`: 鼠标点击
- `MOUSE_MOVE`: 鼠标移动
- `KEYBOARD_TYPE`: 键盘输入
- `KEYBOARD_PRESS`: 按键操作
- `KEYBOARD_HOTKEY`: 组合键
- `WINDOW_LIST`: 列出窗口
- `WINDOW_ACTIVATE`: 激活窗口
- `WINDOW_CLOSE`: 关闭窗口
- `OCR_RECOGNIZE`: OCR识别

#### 1.2 统一 ActionType 枚举

**文件**: `server/agent/config.py`

确保 `ActionType` 枚举包含所有意图检测器支持的操作类型。

#### 1.3 添加 CUA 操作模块

**新建文件**: `server/agent/operations/cua.py`

实现计算机使用代理（CUA）操作：
- 使用 `pyautogui` 进行鼠标键盘控制
- 使用 `Pillow` 进行截图
- 使用 `pytesseract` 或 `easyocr` 进行 OCR

### 第二阶段：增强意图检测（中优先级）

#### 2.1 启用 LLM 辅助意图检测

**文件**: `server/agent/intent/unified_detector.py`

修改 `detect` 方法，在规则匹配置信度低时自动调用 LLM：
```python
def detect(self, message, session_id=None, context=None):
    # 先尝试规则匹配
    result = self._detect_by_rules(message)
    
    # 如果置信度低，使用 LLM 辅助
    if result.confidence < 0.7 and self.llm_client:
        llm_result = await self.detect_with_llm(message, session_id, context)
        if llm_result.confidence > result.confidence:
            result = llm_result
```

#### 2.2 增强上下文参数推断

**文件**: `server/agent/intent/unified_detector.py`

改进 `_resolve_context_references` 方法：
- 支持更多代词引用（"刚才的内容"、"上次的文件"）
- 支持从对话历史中提取参数
- 支持从 AI 生成内容中提取参数

#### 2.3 添加操作模板系统

**新建文件**: `server/agent/templates.py`

定义常见操作模板，简化复杂操作：
```python
OPERATION_TEMPLATES = {
    "save_generated_code": {
        "trigger": ["保存代码", "保存生成的代码", "存一下"],
        "action": "file_write",
        "params_from_context": {
            "content": "last_generated_content",
            "file_path": "infer_from_language"
        }
    }
}
```

### 第三阶段：改进前端交互（中优先级）

#### 3.1 改进 Agent 执行流程

**文件**: `client/src/pages/Chat.tsx`

修改执行逻辑：
1. 先让 AI 响应用户请求
2. AI 响应中如果包含操作意图，再执行操作
3. 执行结果反馈给用户，并允许重试

#### 3.2 增强结果展示

**文件**: `client/src/pages/Chat.tsx`

改进 `formatAgentResult` 函数：
- 显示详细的执行结果（如文件内容预览）
- 失败时显示具体原因和解决建议
- 提供重试和修改参数的选项

#### 3.3 添加操作确认对话框

**文件**: `client/src/components/OperationConfirmModal.tsx`（新建）

创建操作确认组件：
- 显示即将执行的操作详情
- 允许用户修改参数
- 显示操作风险评估

### 第四阶段：安全与权限（低优先级）

#### 4.1 改进应用白名单机制

**文件**: `server/agent/security_old.py`

- 支持用户自定义白名单
- 支持通配符匹配
- 首次打开新应用时请求用户确认

#### 4.2 添加操作审计日志

**文件**: `server/agent/audit.py`

记录所有操作的详细信息：
- 操作类型、参数、结果
- 用户确认记录
- 失败原因和重试记录

#### 4.3 实现沙箱执行模式

**新建文件**: `server/agent/sandbox.py`

为危险操作提供沙箱环境：
- 文件操作限制在特定目录
- 系统命令需要额外确认
- 支持操作回滚

---

## 实施计划

### 第一步：修复执行器缺失操作

1. 扩展 `ActionType` 枚举
2. 实现 CUA 操作模块
3. 更新执行器的 `action_map`

### 第二步：增强意图检测

1. 启用 LLM 辅助检测
2. 改进上下文参数推断
3. 添加操作模板系统

### 第三步：改进前端交互

1. 优化 Agent 执行流程
2. 增强结果展示
3. 添加操作确认对话框

### 第四步：安全加固

1. 改进应用白名单
2. 完善审计日志
3. 实现沙箱模式

---

## 技术依赖

需要添加的 Python 包：
```
pyautogui>=0.9.54  # 鼠标键盘控制
Pillow>=10.0.0     # 截图
pytesseract>=0.3.10  # OCR（可选）
easyocr>=1.7.0     # OCR（替代方案）
pywin32>=306       # Windows 窗口管理（Windows）
```

---

## 预期效果

改进后，用户可以：
1. 使用自然语言请求本地操作（如"帮我把刚才的代码保存到桌面"）
2. 执行屏幕操作（截图、点击、输入）
3. 获得清晰的执行反馈和错误提示
4. 在安全可控的环境下操作本地电脑
