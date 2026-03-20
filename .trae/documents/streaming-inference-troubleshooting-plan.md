# 流式推理无输出故障排查与修复计划

## 问题概述

在使用流式推理功能时遇到模型无输出的问题。经过代码分析，发现了多个可能导致该问题的根本原因。

---

## 一、问题根因分析

### 1. 后端 HuggingFace 流式推理核心问题

**位置**: [inference.py:729-760](file:///c:/Users/JHJ/Desktop/finetune-platform/server/api/inference.py#L729-L760)

**问题描述**:
```python
async def generate() -> AsyncGenerator[str, None]:
    in_think_block = False
    try:
        for text in streamer:  # ⚠️ 同步迭代器阻塞事件循环
            if text:
                # ...
```

**根本原因**:
- `TextIteratorStreamer` 是同步迭代器，在 `async def` 函数中直接使用 `for text in streamer:` 会阻塞 FastAPI 的事件循环
- 这导致 SSE 响应无法正常发送给客户端
- 线程中的 `model.generate()` 可能已完成，但主线程被阻塞无法处理结果

### 2. 思考标签过滤逻辑问题

**位置**: [inference.py:736-745](file:///c:/Users/JHJ/Desktop/finetune-platform/server/api/inference.py#L736-L745)

**问题描述**:
```python
if " " in text:
    in_think_block = True
    text = text.split(" ")[-1] if " " in text else text

if " " in text:
    in_think_block = False
    text = text.split(" ")[-1] if " " in text else text
elif in_think_block:
    text = ""  # 在思考块内，跳过
```

**根本原因**:
- 思考标签 ` ` 和 ` ` 可能被错误匹配
- 如果模型输出包含这些标签，所有内容可能被过滤掉

### 3. 前端 SSE 解析问题

**位置**: [api.ts:507-541](file:///c:/Users/JHJ/Desktop/finetune-platform/client/src/services/api.ts#L507-L541)

**问题描述**:
```typescript
const events = buffer.split('\n\n');
buffer = events.pop() || '';

for (const event of events) {
    const eventLines = event.split('\n');
    let dataLine = '';
    
    for (const line of eventLines) {
        if (line.startsWith('data: ')) {
            dataLine = line.slice(6);
        }
    }
    // ...
}
```

**根本原因**:
- SSE 事件格式为 `event: message\ndata: {...}\n\n`
- 当前解析逻辑没有正确处理 `event:` 行
- 可能导致事件数据解析失败

### 4. 线程异常处理缺失

**位置**: [inference.py:726-727](file:///c:/Users/JHJ/Desktop/finetune-platform/server/api/inference.py#L726-L727)

**问题描述**:
```python
thread = Thread(target=model.generate, kwargs=generation_kwargs)
thread.start()
```

**根本原因**:
- 后台线程中的异常不会被主线程捕获
- 如果 `model.generate()` 失败，前端无法收到错误信息
- 流式推理会静默失败

---

## 二、故障排查步骤

### 步骤 1: 验证后端服务状态

```bash
# 检查后端是否正常运行
curl http://127.0.0.1:8000/health

# 检查模型列表
curl http://127.0.0.1:8000/inference/models

# 检查推理后端状态
curl http://127.0.0.1:8000/inference/backends
```

### 步骤 2: 测试非流式推理

```bash
# 测试非流式推理是否正常
curl -X POST http://127.0.0.1:8000/inference/generate \
  -H "Content-Type: application/json" \
  -d '{
    "modelId": "your-model-id",
    "prompt": "你好",
    "maxTokens": 100,
    "temperature": 0.7
  }'
```

### 步骤 3: 检查日志输出

```bash
# 查看后端日志
# 日志位置: server/logs/ 目录

# 关键日志关键词:
# - "加载模型"
# - "流式推理"
# - "TextIteratorStreamer"
# - "应用 chat template"
```

### 步骤 4: 验证模型加载状态

```bash
# 检查模型缓存状态
curl http://127.0.0.1:8000/inference/cache/status
```

### 步骤 5: 测试流式推理端点

```bash
# 使用 curl 测试流式端点
curl -X POST http://127.0.0.1:8000/inference/stream \
  -H "Content-Type: application/json" \
  -d '{
    "modelId": "your-model-id",
    "prompt": "你好",
    "maxTokens": 100
  }'
```

---

## 三、修复方案

### 修复 1: 使用 asyncio.to_thread 包装同步迭代器

**文件**: `server/api/inference.py`

**修改内容**:
```python
async def generate() -> AsyncGenerator[str, None]:
    in_think_block = False
    try:
        # 使用 asyncio 运行同步迭代器
        def get_next_token():
            try:
                return next(streamer)
            except StopIteration:
                return None
        
        while True:
            text = await asyncio.to_thread(get_next_token)
            if text is None:
                break
            
            if text:
                # ... 处理逻辑
```

### 修复 2: 添加线程异常捕获机制

**文件**: `server/api/inference.py`

**修改内容**:
```python
generation_error = None

def generate_with_error_handling():
    nonlocal generation_error
    try:
        model.generate(**generation_kwargs)
    except Exception as e:
        generation_error = e
        logger.error(f"生成线程错误: {e}", exc_info=True)

thread = Thread(target=generate_with_error_handling)
thread.start()

# 在迭代过程中检查错误
while True:
    text = await asyncio.to_thread(get_next_token)
    if text is None:
        break
    if generation_error:
        raise generation_error
```

### 修复 3: 修复思考标签过滤逻辑

**文件**: `server/api/inference.py`

**修改内容**:
```python
# 使用正确的 Unicode 思考标签
THINK_START = "\u003cthink\u003e"  # <think
THINK_END = "\u003c/think\u003e"   # </think

# 或者直接使用字符串
THINK_START = "<think"
THINK_END = "</think"

# 改进过滤逻辑
def filter_think_block(text: str, in_think_block: bool) -> tuple[str, bool]:
    """过滤思考块内容"""
    if THINK_START in text:
        in_think_block = True
        text = text.split(THINK_START)[-1] if THINK_START in text else text
    
    if THINK_END in text:
        in_think_block = False
        text = text.split(THINK_END)[-1] if THINK_END in text else text
    elif in_think_block:
        text = ""
    
    return text, in_think_block
```

### 修复 4: 改进前端 SSE 解析

**文件**: `client/src/services/api.ts`

**修改内容**:
```typescript
// 改进 SSE 事件解析
const parseSSEEvent = (eventStr: string): { event: string; data: string } | null => {
    const lines = eventStr.split('\n');
    let eventType = 'message';
    let dataLine = '';
    
    for (const line of lines) {
        if (line.startsWith('event: ')) {
            eventType = line.slice(7);
        } else if (line.startsWith('data: ')) {
            dataLine = line.slice(6);
        }
    }
    
    return dataLine ? { event: eventType, data: dataLine } : null;
};

// 使用改进的解析器
for (const event of events) {
    const parsed = parseSSEEvent(event);
    if (parsed) {
        try {
            const data = JSON.parse(parsed.data);
            // 处理数据
        } catch (e) {
            console.error('Parse SSE error:', e);
        }
    }
}
```

### 修复 5: 添加详细日志记录

**文件**: `server/api/inference.py`

**修改内容**:
```python
logger.info(f"开始流式推理 - 模型: {request.get_model_id()}, 后端: {backend}")
logger.info(f"生成参数 - max_tokens: {request.get_max_tokens()}, temperature: {request.temperature}")
logger.debug(f"Chat template 应用后: {formatted_prompt[:200]}...")

# 在流式输出过程中
chunk_count = 0
for text in streamer:
    chunk_count += 1
    logger.debug(f"收到 chunk #{chunk_count}: {text[:50]}...")
    # ...

logger.info(f"流式推理完成 - 共 {chunk_count} 个 chunks")
```

---

## 四、实施计划

### 阶段 1: 紧急修复（优先级：高）

1. **修复同步迭代器阻塞问题**
   - 文件: `server/api/inference.py`
   - 使用 `asyncio.to_thread` 包装 `TextIteratorStreamer`
   - 预计耗时: 30 分钟

2. **添加线程异常捕获**
   - 文件: `server/api/inference.py`
   - 确保错误能正确传递给前端
   - 预计耗时: 15 分钟

### 阶段 2: 功能优化（优先级：中）

3. **修复思考标签过滤**
   - 文件: `server/api/inference.py`
   - 使用正确的 Unicode 标签
   - 预计耗时: 20 分钟

4. **改进前端 SSE 解析**
   - 文件: `client/src/services/api.ts`
   - 添加更健壮的事件解析
   - 预计耗时: 30 分钟

### 阶段 3: 增强监控（优先级：低）

5. **添加详细日志**
   - 文件: `server/api/inference.py`
   - 记录关键步骤和性能指标
   - 预计耗时: 15 分钟

6. **添加健康检查端点**
   - 新增 `/inference/stream/health` 端点
   - 返回流式推理组件状态
   - 预计耗时: 30 分钟

---

## 五、验证测试

### 测试用例 1: 基本流式推理

```bash
# 测试基本流式推理功能
curl -N -X POST http://127.0.0.1:8000/inference/stream \
  -H "Content-Type: application/json" \
  -d '{"modelId": "test-model", "prompt": "你好", "maxTokens": 50}'
```

**预期结果**: 应该看到 SSE 格式的流式输出

### 测试用例 2: 长文本生成

```bash
# 测试长文本生成
curl -N -X POST http://127.0.0.1:8000/inference/stream \
  -H "Content-Type: application/json" \
  -d '{"modelId": "test-model", "prompt": "写一个故事", "maxTokens": 500}'
```

**预期结果**: 应该持续输出直到完成

### 测试用例 3: 错误处理

```bash
# 测试错误情况
curl -N -X POST http://127.0.0.1:8000/inference/stream \
  -H "Content-Type: application/json" \
  -d '{"modelId": "non-existent", "prompt": "test", "maxTokens": 10}'
```

**预期结果**: 应该返回错误信息，而不是静默失败

### 测试用例 4: 前端集成测试

1. 打开前端应用
2. 选择模型
3. 输入测试问题
4. 观察流式输出是否正常显示

---

## 六、回滚计划

如果修复后出现新问题:

1. 恢复 `server/api/inference.py` 到原始版本
2. 恢复 `client/src/services/api.ts` 到原始版本
3. 重启后端服务
4. 验证非流式推理功能正常

---

## 七、相关文件清单

| 文件 | 修改内容 | 优先级 |
|------|----------|--------|
| `server/api/inference.py` | 修复流式推理核心逻辑 | 高 |
| `client/src/services/api.ts` | 改进 SSE 解析 | 中 |
| `server/core/streaming.py` | 优化流式工具类 | 低 |
| `server/core/config.py` | 添加流式配置项 | 低 |

---

## 八、注意事项

1. **线程安全**: 确保 `TextIteratorStreamer` 在多线程环境下的安全性
2. **内存管理**: 长时间流式输出时注意内存使用
3. **超时处理**: 设置合理的超时时间，避免无限等待
4. **错误传递**: 确保所有错误都能正确传递给前端
5. **日志级别**: 生产环境使用 INFO 级别，开发环境使用 DEBUG 级别
