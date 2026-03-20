# Finetune Platform API 使用指南

## 基础信息

- **Base URL**: `http://localhost:8000`
- **API 文档**: `http://localhost:8000/docs` (Swagger UI)
- **ReDoc**: `http://localhost:8000/redoc`

## 认证

当前版本不需要认证，预留扩展。

## 端点概览

### 设备管理 `/device`

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/device/info` | 获取设备信息 |
| GET | `/device/vram` | 获取 VRAM 信息 |
| GET | `/device/memory` | 获取系统内存信息 |
| GET | `/device/disk` | 获取磁盘信息 |

### 模型管理 `/models`

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/models` | 列出模型 |
| POST | `/models/download` | 下载模型 |
| GET | `/models/download/status` | 获取下载状态 |
| GET | `/models/{model_id}` | 获取模型详情 |
| DELETE | `/models/{model_id}` | 删除模型 |
| POST | `/models/{model_id}/export/onnx` | 导出 ONNX |
| GET | `/models/stats` | 获取模型统计 |

### 数据集管理 `/datasets`

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/datasets` | 列出数据集 |
| POST | `/datasets/upload` | 上传数据集 |
| GET | `/datasets/{dataset_id}` | 获取数据集详情 |
| DELETE | `/datasets/{dataset_id}` | 删除数据集 |
| GET | `/datasets/{dataset_id}/preview` | 预览数据集 |
| GET | `/datasets/{dataset_id}/statistics` | 获取统计信息 |

### 训练管理 `/training`

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/training/start` | 开始训练 |
| POST | `/training/stop` | 停止训练 |
| GET | `/training/progress` | 获取进度 |
| GET | `/training/progress/stream` | SSE 进度流 |
| GET | `/training/history` | 训练历史 |
| GET | `/training/status` | 训练状态 |
| GET | `/training/checkpoints/{task_id}` | 获取检查点 |
| POST | `/training/resume/{task_id}/{checkpoint}` | 从检查点恢复 |

### 推理服务 `/inference`

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/inference/generate` | 文本生成 |
| POST | `/inference/chat` | 聊天对话 |
| POST | `/inference/stream` | 流式生成 |
| GET | `/inference/backends` | 获取后端列表 |
| POST | `/inference/backends/switch` | 切换后端 |
| GET | `/inference/models` | 获取可用模型 |
| GET | `/inference/ollama/status` | Ollama 状态 |
| POST | `/inference/merge` | 合并 LoRA |
| GET | `/inference/merge/status` | 合并状态 |

## 使用示例

### 1. 健康检查

```bash
curl http://localhost:8000/health
```

响应：
```json
{
  "status": "healthy",
  "timestamp": "2024-01-01T12:00:00",
  "version": "2.0.0",
  "cuda_available": true,
  "gpu_info": {
    "device_name": "NVIDIA GeForce RTX 3090",
    "memory": {
      "total_gb": 24.0,
      "allocated_gb": 0.5,
      "reserved_gb": 1.0
    }
  }
}
```

### 2. 下载模型

```bash
curl -X POST http://localhost:8000/models/download \
  -H "Content-Type: application/json" \
  -d '{
    "model_name": "Qwen/Qwen2.5-0.5B-Instruct",
    "revision": "main",
    "quantize": 4,
    "use_safetensors": true
  }'
```

### 3. 上传数据集

```bash
curl -X POST http://localhost:8000/datasets/upload \
  -F "file=@dataset.json" \
  -F "name=my_dataset" \
  -F "description=我的测试数据集"
```

### 4. 开始训练

```bash
curl -X POST http://localhost:8000/training/start \
  -H "Content-Type: application/json" \
  -d '{
    "model_id": "Qwen--Qwen2.5-0.5B-Instruct",
    "dataset_id": "my_dataset",
    "method": "qlora",
    "rank": 8,
    "alpha": 16,
    "learning_rate": 5e-5,
    "epochs": 3,
    "batch_size": 1,
    "gradient_accumulation": 16,
    "max_seq_length": 512,
    "warmup_steps": 100,
    "save_steps": 500,
    "logging_steps": 10,
    "quantization": 4
  }'
```

### 5. 获取训练进度

```bash
curl http://localhost:8000/training/progress
```

响应：
```json
{
  "epoch": 1,
  "step": 100,
  "total_steps": 1000,
  "loss": 2.5,
  "lr": 0.00005,
  "vram_used": 4.2,
  "elapsed_time": 120.5,
  "eta": 1080.0,
  "status": "running",
  "message": "Training epoch 1/3"
}
```

### 6. 文本生成

```bash
curl -X POST http://localhost:8000/inference/generate \
  -H "Content-Type: application/json" \
  -d '{
    "model_id": "Qwen--Qwen2.5-0.5B-Instruct",
    "prompt": "你好，请介绍一下自己",
    "max_tokens": 512,
    "temperature": 0.7,
    "top_p": 0.9,
    "backend": "huggingface"
  }'
```

### 7. 聊天对话

```bash
curl -X POST http://localhost:8000/inference/chat \
  -H "Content-Type: application/json" \
  -d '{
    "model_id": "Qwen--Qwen2.5-0.5B-Instruct",
    "messages": [
      {"role": "system", "content": "你是一个有帮助的助手"},
      {"role": "user", "content": "你好"}
    ],
    "max_tokens": 512,
    "temperature": 0.7
  }'
```

### 8. SSE 流式输出

```bash
curl -N http://localhost:8000/inference/stream \
  -H "Content-Type: application/json" \
  -d '{
    "model_id": "Qwen--Qwen2.5-0.5B-Instruct",
    "prompt": "写一首诗",
    "max_tokens": 256
  }'
```

### 9. 从检查点恢复训练

```bash
# 首先获取检查点列表
curl http://localhost:8000/training/checkpoints/{task_id}

# 从检查点恢复
curl -X POST http://localhost:8000/training/resume/{task_id}/checkpoint-500
```

## Python SDK 示例

```python
import requests
import time

BASE_URL = "http://localhost:8000"

# 健康检查
response = requests.get(f"{BASE_URL}/health")
print(response.json())

# 开始训练
train_config = {
    "model_id": "Qwen--Qwen2.5-0.5B-Instruct",
    "dataset_id": "my_dataset",
    "method": "qlora",
    "epochs": 3,
    "batch_size": 1,
    "learning_rate": 5e-5,
}

response = requests.post(f"{BASE_URL}/training/start", json=train_config)
task_id = response.json()["id"]
print(f"训练任务已启动：{task_id}")

# 轮询进度
while True:
    response = requests.get(f"{BASE_URL}/training/progress")
    progress = response.json()
    print(f"进度：{progress['step']}/{progress['total_steps']} - Loss: {progress['loss']:.4f}")
    
    if progress["status"] in ["completed", "failed", "stopped"]:
        break
    
    time.sleep(5)

# 推理测试
inference_request = {
    "model_id": "Qwen--Qwen2.5-0.5B-Instruct",
    "prompt": "你好",
    "max_tokens": 256,
}

response = requests.post(f"{BASE_URL}/inference/generate", json=inference_request)
print(f"生成结果：{response.json()['text']}")
```

## 错误处理

### 常见错误码

| 状态码 | 说明 |
|--------|------|
| 400 | 请求参数错误 |
| 404 | 资源不存在 |
| 409 | 资源冲突（如已存在） |
| 429 | 速率限制超限 |
| 500 | 服务器内部错误 |
| 503 | 服务不可用 |

### 错误响应格式

```json
{
  "error": "HTTP 400",
  "detail": "具体的错误信息"
}
```

## 速率限制

- 默认：100 请求/分钟
- 可通过环境变量调整：
  - `RATE_LIMIT`: 请求数
  - `RATE_WINDOW`: 时间窗口（秒）

## 最佳实践

1. **训练前检查 VRAM**：确保有足够显存
2. **使用小数据集测试**：先验证配置
3. **定期检查进度**：使用 SSE 流式获取实时进度
4. **保存检查点**：重要训练任务启用检查点
5. **清理缓存**：推理后调用 `/inference/cache/clear` 释放显存
