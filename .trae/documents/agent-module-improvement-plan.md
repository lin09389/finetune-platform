# Agent 模块操作改进计划

## 问题概述

通过分析发现，agent 模块存在以下核心问题导致无法自如操作本地电脑：

### 问题清单

| 类别 | 问题 | 严重程度 | 文件位置 |
|-----|------|---------|---------|
| 执行器缺失 | file_copy/move/rename/search 未实现 | 高 | executor.py |
| API 问题 | session_id 未传递，上下文丢失 | 中 | api/agent.py |
| 安全过严 | URL/文件路径/应用白名单限制 | 中 | security_old.py, config.py |
| 前端问题 | 无超时、错误处理不完善 | 中 | Chat.tsx |
| 编码问题 | 中文乱码 | 低 | operations/file/*.py |

---

## 改进计划

### 第一阶段：完善执行器操作实现（高优先级）

#### 1.1 集成现有文件操作模块

**文件**: `server/agent/executor.py`

项目中已存在但未被集成的模块：
- `server/agent/operations/file/copy.py` - 文件复制
- `server/agent/operations/file/move.py` - 文件移动
- `server/agent/operations/file/rename.py` - 文件重命名

需要：
1. 在 `action_map` 中添加这些操作
2. 实现对应的 `_file_copy`、`_file_move`、`_file_rename` 方法
3. 调用现有的 operations 模块

#### 1.2 添加缺失的操作实现

**文件**: `server/agent/executor.py`

需要新增：
- `FILE_SEARCH`: 文件搜索
- `PROCESS_LIST`: 进程列表
- `DIRECTORY_CREATE`: 创建目录
- `DIRECTORY_DELETE`: 删除目录
- `CLIPBOARD_READ`: 读取剪贴板
- `CLIPBOARD_WRITE`: 写入剪贴板

#### 1.3 修复编码问题

**文件**: 
- `server/agent/operations/file/copy.py`
- `server/agent/operations/file/move.py`
- `server/agent/operations/file/rename.py`

确保文件使用 UTF-8 编码，修复中文乱码。

---

### 第二阶段：修复 API 端点问题（中优先级）

#### 2.1 传递 session_id

**文件**: `server/api/agent.py`

修改 `chat_execute` 函数：
```python
# 当前代码（有问题）
intent = detector.detect(request.message, context=request.context)

# 修改为
intent = detector.detect(
    request.message, 
    session_id=request.session_id,  # 添加 session_id
    context=request.context
)
```

#### 2.2 改进 ActionType 转换错误处理

**文件**: `server/api/agent.py`

当 intent.action 不在 ActionType 枚举中时，返回可用操作列表：
```python
except ValueError:
    available_actions = [a.value for a in ActionType]
    return ChatExecuteResponse(
        detected=True,
        action=intent.action,
        description=intent.description,
        error=f"不支持的操作类型：{intent.action}。可用操作：{', '.join(available_actions)}"
    )
```

#### 2.3 完善 context 处理

**文件**: `server/api/agent.py`

增强上下文信息传递，包括：
- last_generated_content
- last_file_path
- recent_operations

---

### 第三阶段：放宽安全验证（中优先级）

#### 3.1 添加开发模式配置

**文件**: `server/agent/config.py`

```python
class SecurityConfig(BaseModel):
    allow_localhost: bool = True  # 允许访问 localhost
    allow_intranet: bool = False  # 允许访问内网
    allowed_directories: List[str] = []  # 额外允许的目录
    strict_path_check: bool = False  # 严格路径检查
```

#### 3.2 改进 URL 验证

**文件**: `server/agent/security_old.py`

```python
def validate_url(self, url: str, allow_localhost: bool = True) -> ValidationResult:
    # 根据 allow_localhost 配置决定是否允许 localhost
    if allow_localhost:
        forbidden_hosts = []  # 开发模式不禁止
    else:
        forbidden_hosts = ["localhost", "127.0.0.1", ...]
```

#### 3.3 改进文件路径验证

**文件**: `server/agent/security_old.py`

支持配置允许访问的额外目录：
```python
def validate_path(self, file_path: str, action: ActionType, allowed_dirs: List[str] = None) -> ValidationResult:
    # 检查是否在允许的目录列表中
    if allowed_dirs:
        for allowed_dir in allowed_dirs:
            if str(full_path).startswith(allowed_dir):
                return ValidationResult(True, sanitized_value=str(full_path))
```

---

### 第四阶段：改进前端交互（中优先级）

#### 4.1 添加请求超时

**文件**: `client/src/pages/Chat.tsx`

```typescript
const executeAgent = async (
  userMessage: string, 
  context?: {...},
  timeout: number = 30000  // 30秒超时
): Promise<{...}> => {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);
  
  try {
    const result = await chatExecuteAgent(userMessage, false, context, controller.signal);
    clearTimeout(timeoutId);
    return result;
  } catch (error) {
    if (error.name === 'AbortError') {
      message.error('操作超时，请重试');
    }
    // ...
  }
}
```

#### 4.2 改进错误显示

**文件**: `client/src/pages/Chat.tsx`

```typescript
catch (error) {
  // 当前：只打印到控制台
  console.error('Agent 执行失败:', error)
  
  // 改进：显示给用户
  const errorMsg = error instanceof Error ? error.message : '未知错误'
  message.error(`操作失败：${errorMsg}`)
  setAgentExecution({ status: 'failed', error: errorMsg })
}
```

#### 4.3 传递 context 到确认对话框

**文件**: `client/src/pages/Chat.tsx`

确保 `confirmDangerousAction` 函数传递之前的 context 参数。

---

### 第五阶段：添加缺失的意图检测规则（低优先级）

#### 5.1 添加剪贴板操作规则

**文件**: `server/agent/intent/unified_detector.py`

```python
{
    "action": "clipboard_read",
    "pattern": r"(?:读取|获取|查看)(?:剪贴板|剪贴板内容)",
    "params": lambda m: {}
},
{
    "action": "clipboard_write", 
    "pattern": r"(?:复制|写入|设置)(.+?)(?:到剪贴板|到剪贴板)",
    "params": lambda m: {"content": m.group(1)}
}
```

#### 5.2 添加目录操作规则

```python
{
    "action": "directory_create",
    "pattern": r"(?:创建|新建|建立)(.+?)(?:文件夹|目录)",
    "params": lambda m: {"directory": m.group(1)}
},
{
    "action": "directory_delete",
    "pattern": r"(?:删除|移除)(.+?)(?:文件夹|目录)",
    "params": lambda m: {"directory": m.group(1), "confirmed": False}
}
```

#### 5.3 添加压缩操作规则

```python
{
    "action": "file_compress",
    "pattern": r"(?:压缩|打包)(.+?)(?:为|到)(.+?)",
    "params": lambda m: {"source": m.group(1), "target": m.group(2)}
},
{
    "action": "file_extract",
    "pattern": r"(?:解压|解包)(.+?)(?:到|至)(.+?)",
    "params": lambda m: {"source": m.group(1), "target": m.group(2)}
}
```

---

## 实施顺序

```
第一阶段（高优先级）
├── 1.1 集成现有文件操作模块
├── 1.2 添加缺失的操作实现
└── 1.3 修复编码问题

第二阶段（中优先级）
├── 2.1 传递 session_id
├── 2.2 改进 ActionType 转换错误处理
└── 2.3 完善 context 处理

第三阶段（中优先级）
├── 3.1 添加开发模式配置
├── 3.2 改进 URL 验证
└── 3.3 改进文件路径验证

第四阶段（中优先级）
├── 4.1 添加请求超时
├── 4.2 改进错误显示
└── 4.3 传递 context 到确认对话框

第五阶段（低优先级）
├── 5.1 添加剪贴板操作规则
├── 5.2 添加目录操作规则
└── 5.3 添加压缩操作规则
```

---

## 预期效果

改进后，用户可以：

1. **文件操作**: 复制、移动、重命名、搜索文件
2. **目录操作**: 创建、删除目录
3. **剪贴板操作**: 读取、写入剪贴板内容
4. **进程管理**: 查看进程列表
5. **更宽松的安全策略**: 支持开发模式，允许访问更多目录
6. **更好的错误提示**: 明确告知用户操作失败原因和解决方法
7. **多轮对话上下文**: 正确传递 session_id，保持对话连贯性

---

## 技术依赖

可能需要添加的 Python 包：
```
pyperclip>=1.8.2  # 剪贴板操作
```
