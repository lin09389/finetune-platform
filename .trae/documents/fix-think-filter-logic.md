# 修复思考标签过滤逻辑问题

## 问题分析

### 测试结果

```
event: message
data: {"content": " \n", "done": false}

event: done
data: {"done": true, "stats": {"total_tokens": 2, "chunk_count": 1, ...}}
```

模型输出了 ` \n`（思考标签的开始部分），但流式推理只输出了这一个 chunk 就结束了。

### 当前代码问题

**位置**: [inference.py:741-757](file:///c:/Users/JHJ/Desktop/finetune-platform/server/api/inference.py#L741-L757)

```python
THINK_START = "<think"
THINK_END = "</think"

def filter_think_block(text: str, in_think_block: bool) -> tuple:
    if THINK_START in text:
        in_think_block = True
        parts = text.split(THINK_START)
        text = parts[-1] if len(parts) > 1 else text  # ❌ 问题：保留了分割后的内容
    
    if THINK_END in text:
        in_think_block = False
        parts = text.split(THINK_END)
        text = parts[-1] if len(parts) > 1 else text
    elif in_think_block:
        text = ""  # ❌ 问题：这会清空后续所有内容
    
    return text, in_think_block
```

### 问题根因

1. **检测到思考块开始时处理不当**：
   - 当文本包含 `<think` 时，应该立即清空当前文本
   - 但当前代码保留了 `split` 后的最后一部分

2. **思考块内容被错误处理**：
   - ` \n` 包含 `<think`，被检测到后 `in_think_block = True`
   - 分割后得到 `\n`，但由于 `in_think_block = True`，后续内容被清空

3. **逻辑顺序问题**：
   - 先检测开始标签，再检测结束标签
   - 但如果在同一个 chunk 中同时包含开始和结束标签，处理会有问题

---

## 修复方案

### 方案 1: 修复过滤逻辑

```python
THINK_START = "<think"
THINK_END = "</think"

def filter_think_block(text: str, in_think_block: bool) -> tuple:
    # 先检查结束标签（优先处理结束）
    if THINK_END in text:
        in_think_block = False
        parts = text.split(THINK_END)
        text = parts[-1] if len(parts) > 1 else ""
    elif in_think_block:
        # 在思考块内，清空文本
        text = ""
    
    # 再检查开始标签
    if THINK_START in text:
        in_think_block = True
        # 清空开始标签之前的内容
        parts = text.split(THINK_START)
        text = ""  # 直接清空，不保留任何内容
    
    return text, in_think_block
```

### 方案 2: 更健壮的实现

```python
THINK_START = "<think"
THINK_END = "</think"

def filter_think_block(text: str, in_think_block: bool) -> tuple:
    result = ""
    i = 0
    
    while i < len(text):
        if not in_think_block and text[i:].startswith(THINK_START):
            # 检测到思考块开始
            in_think_block = True
            i += len(THINK_START)
            # 跳过到 > 之后
            gt_pos = text.find('>', i)
            if gt_pos != -1:
                i = gt_pos + 1
            continue
        
        if in_think_block and text[i:].startswith(THINK_END):
            # 检测到思考块结束
            in_think_block = False
            i += len(THINK_END)
            # 跳过到 > 之后
            gt_pos = text.find('>', i)
            if gt_pos != -1:
                i = gt_pos + 1
            continue
        
        if not in_think_block:
            result += text[i]
        
        i += 1
    
    return result, in_think_block
```

### 方案 3: 简化版（推荐）

```python
THINK_START = "<think"
THINK_END = "</think"

def filter_think_block(text: str, in_think_block: bool) -> tuple:
    # 如果在思考块内，先检查是否有结束标签
    if in_think_block:
        if THINK_END in text:
            # 思考块结束，取结束标签之后的内容
            in_think_block = False
            idx = text.find(THINK_END)
            text = text[idx + len(THINK_END):]
            # 跳过可能的 > 字符
            if text.startswith(">"):
                text = text[1:]
        else:
            # 仍在思考块内，清空
            return "", True
    
    # 检查是否有新的思考块开始
    if THINK_START in text:
        in_think_block = True
        idx = text.find(THINK_START)
        # 只保留开始标签之前的内容
        text = text[:idx]
    
    return text, in_think_block
```

---

## 实施步骤

### 步骤 1: 修改 inference.py 中的过滤函数

**文件**: `server/api/inference.py`

替换 `filter_think_block` 函数为方案 3 的实现。

### 步骤 2: 同步修改 huggingface_engine.py

**文件**: `server/core/inference/huggingface_engine.py`

在 `_clean_response` 方法中也需要类似的修复。

### 步骤 3: 添加单元测试

创建测试用例验证过滤逻辑：

```python
def test_filter_think_block():
    # 测试开始标签
    assert filter_think_block(" \n", False) == ("", True)
    
    # 测试结束标签
    assert filter_think_block(" Hello", True) == (" Hello", False)
    
    # 测试完整思考块
    assert filter_think_block(" thinking Hello", False) == (" Hello", False)
    
    # 测试无思考块
    assert filter_think_block("Hello World", False) == ("Hello World", False)
```

---

## 验证测试

修复后重新测试流式推理：

```bash
$body = '{"modelId":"Qwen3.5-2B","prompt":"你好","maxTokens":50,"temperature":0.7}'
Invoke-WebRequest -Uri "http://127.0.0.1:8000/inference/stream" -Method Post -ContentType "application/json" -Body $body -UseBasicParsing
```

**预期结果**: 应该看到完整的模型回复，而不是只有思考标签。

---

## 相关文件

| 文件 | 修改内容 |
|------|----------|
| `server/api/inference.py` | 修复 `filter_think_block` 函数 |
| `server/core/inference/huggingface_engine.py` | 修复 `_clean_response` 方法 |
