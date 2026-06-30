# 本地推理部署说明

## 快速开始

1. 在仓库根目录安装后端依赖：

```bash
uv sync
```

2. 启动后端：

```bash
uv run python -m uvicorn server.main:app --host 127.0.0.1 --port 8010
```

3. 打开前端推理页，选择本地后端与模型。

## 本地能力

- REST: `POST /inference/chat`、`POST /inference/generate`
- 流式 REST: `POST /inference/chat/stream`、`POST /inference/generate/stream`
- OpenAI 兼容 API: `GET /v1/models`、`POST /v1/chat/completions`
- Prometheus: `GET /inference/metrics`
- 缓存与预热状态: `GET /inference/cache/status`
- 可选 gRPC: 设置 `ENABLE_INFERENCE_GRPC=true`

## OpenAI SDK 接入

`/v1/models` 聚合 HuggingFace、Ollama、llama.cpp 和已激活部署别名。模型名称跨后端重复时，接口会返回形如 `ollama/qwen3:8b` 的 `canonical_id`，用它可以无歧义路由；通常无需传非标准请求头。

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:8010/v1",
    # ENABLE_AUTH=true 时填平台签发的 JWT；关闭认证的本地开发环境可填任意非空值。
    api_key="YOUR_PLATFORM_JWT",
)

models = client.models.list()
response = client.chat.completions.create(
    model=models.data[0].id,
    messages=[{"role": "user", "content": "你好"}],
    temperature=0,
    stream=True,
)
for chunk in response:
    print(chunk.choices[0].delta.content or "", end="")
```

当前本地后端支持文本聊天、流式输出、`temperature`、`top_p`、`max_tokens` / `max_completion_tokens`、`stop` 和 `stream_options.include_usage`。工具调用、非文本消息、`n > 1`、JSON response format、presence/frequency penalty、seed 与 logit bias 会返回明确的 OpenAI 格式 `400` 错误，不会被静默忽略。

## gRPC

- 地址配置：
  - `INFERENCE_GRPC_HOST`
  - `INFERENCE_GRPC_PORT`
- 当前实现为 JSON over gRPC 的最小服务骨架，便于本地工具或桥接层接入。

## 调优建议

- 4-8GB 显存：优先 `llama-cpp` + GGUF/INT4
- 中高显存：优先 HuggingFace + 自动量化
- 低温度问答请求可利用离线缓存减少重复延迟
