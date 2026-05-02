# 本地推理部署说明

## 快速开始

1. 安装后端依赖：

```bash
pip install -r server/requirements.txt
```

2. 启动后端：

```bash
cd server
python -m uvicorn main:app --host 127.0.0.1 --port 8010
```

3. 打开前端推理页，选择本地后端与模型。

## 本地能力

- REST: `POST /inference/chat`、`POST /inference/generate`
- 流式 REST: `POST /inference/chat/stream`、`POST /inference/generate/stream`
- Prometheus: `GET /inference/metrics`
- 缓存与预热状态: `GET /inference/cache/status`
- 可选 gRPC: 设置 `ENABLE_INFERENCE_GRPC=true`

## gRPC

- 地址配置：
  - `INFERENCE_GRPC_HOST`
  - `INFERENCE_GRPC_PORT`
- 当前实现为 JSON over gRPC 的最小服务骨架，便于本地工具或桥接层接入。

## 调优建议

- 4-8GB 显存：优先 `llama-cpp` + GGUF/INT4
- 中高显存：优先 HuggingFace + 自动量化
- 低温度问答请求可利用离线缓存减少重复延迟
