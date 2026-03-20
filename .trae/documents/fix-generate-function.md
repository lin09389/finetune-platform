# 修复 inference.py 中 generate 函数的问题

## 问题概述

`generate` 函数存在以下问题：
1. LoRA 适配器功能未实现
2. top_k 参数未传递给 HuggingFace 后端
3. Ollama 后端缺少 top_k 和 repetition_penalty 参数支持

## 修复步骤

### 步骤 1：修复 ollama_inference 函数
- 添加 `top_k` 和 `repetition_penalty` 参数
- 在请求体中传递这些参数给 Ollama API

### 步骤 2：修复 generate 函数 - Ollama 后端部分
- 调用 `ollama_inference` 时传递 `top_k` 和 `repetition_penalty` 参数

### 步骤 3：修复 generate 函数 - HuggingFace 后端部分
- 在 `model.generate()` 调用中添加 `top_k` 参数
- 实现 LoRA 适配器加载和推理功能

### 步骤 4：实现 LoRA 适配器推理功能
- 检查请求中是否有 LoRA 适配器路径
- 如果有，加载 LoRA 适配器并与基础模型合并
- 使用合并后的模型进行推理
- 考虑 LoRA 适配器的缓存机制（已有 `lora_adapter_cache` 变量）

## 详细实现

### 1. ollama_inference 函数修改

```python
def ollama_inference(
    model: str,
    prompt: str,
    max_tokens: int,
    temperature: float,
    top_p: float,
    top_k: int = 40,  # 添加默认值
    repetition_penalty: float = 1.1,  # 添加默认值
) -> Dict[str, Any]:
    """Ollama 推理"""
    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "think": False,
                "options": {
                    "num_predict": max_tokens,
                    "temperature": temperature,
                    "top_p": top_p,
                    "top_k": top_k,
                    "repeat_penalty": repetition_penalty,
                }
            },
            timeout=300,
        )
        # ... 其余代码不变
```

### 2. generate 函数 - Ollama 后端修改

```python
result = ollama_inference(
    model=request.get_model_id(),
    prompt=request.prompt,
    max_tokens=request.get_max_tokens(),
    temperature=request.temperature,
    top_p=request.get_top_p(),
    top_k=request.get_top_k(),  # 添加
    repetition_penalty=request.get_repetition_penalty(),  # 添加
)
```

### 3. generate 函数 - HuggingFace 后端修改

```python
# 加载模型
model_data = load_model_for_inference(request.get_model_id())
model = model_data["model"]
tokenizer = model_data["tokenizer"]

# 检查并加载 LoRA 适配器
lora_adapter = request.get_lora_adapter()
if lora_adapter:
    model = load_lora_adapter(model, lora_adapter)

# ... 推理代码

with torch.no_grad():
    outputs = model.generate(
        **inputs,
        max_new_tokens=request.get_max_tokens(),
        temperature=request.temperature,
        top_p=request.get_top_p(),
        top_k=request.get_top_k(),  # 添加 top_k
        do_sample=request.temperature > 0,
        repetition_penalty=request.get_repetition_penalty(),
        pad_token_id=tokenizer.pad_token_id,
        eos_token_id=tokenizer.eos_token_id,
    )
```

### 4. 新增 load_lora_adapter 函数

```python
def load_lora_adapter(model, lora_path: str):
    """加载 LoRA 适配器"""
    try:
        from peft import PeftModel
        
        # 检查缓存
        if lora_path in lora_adapter_cache:
            logger.info(f"从缓存加载 LoRA 适配器：{lora_path}")
            return lora_adapter_cache[lora_path]
        
        # 加载 LoRA 适配器
        lora_model = PeftModel.from_pretrained(model, lora_path)
        lora_adapter_cache[lora_path] = lora_model
        
        logger.info(f"LoRA 适配器加载完成：{lora_path}")
        return lora_model
    except Exception as e:
        logger.error(f"加载 LoRA 适配器失败：{e}")
        raise HTTPException(status_code=500, detail=f"加载 LoRA 适配器失败：{str(e)}")
```

## 注意事项

1. LoRA 适配器路径需要验证是否存在
2. LoRA 适配器缓存需要考虑内存管理
3. Ollama API 的参数名称可能与 HuggingFace 不同（如 `repeat_penalty` vs `repetition_penalty`）
4. 需要确保 `peft` 库已安装

## 文件修改清单

- `server/api/inference.py`
  - 修改 `ollama_inference` 函数（约第273-310行）
  - 修改 `generate` 函数（约第353-431行）
  - 新增 `load_lora_adapter` 函数
