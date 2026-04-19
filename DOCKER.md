# Docker 体验版发布说明

本文档描述 Finetune Platform 2.0 的 Docker 体验版启动、验证和常见维护命令。

本体验版优先保证核心 GA 链路可打开、可观察、可验证：模型管理、数据集、训练状态、推理/聊天、知识库。Beta 和 Experimental 页面会继续显示，但不作为本轮 Docker 体验版验收主线。

## 端口

| 服务 | 地址 | 说明 |
| --- | --- | --- |
| 前端 | http://localhost:5173 | Nginx 托管的生产版前端 |
| 后端 API | http://localhost:8000 | FastAPI 服务与 Swagger 文档 |
| Ollama | http://localhost:11434 | 可选，仅启用 Ollama profile 时暴露 |

## 一键启动默认体验栈

默认体验栈包含后端 API 和生产版前端，不强制要求 GPU。

```bash
docker compose up -d --build
```

启动后访问：

- 前端：http://localhost:5173
- API 文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/health

## 验证体验版

```bash
python scripts/verify_docker_release.py
```

脚本会检查：

- 前端页面是否可访问
- `/health`
- `/runtime/bootstrap`
- 模型、数据集、训练状态、推理后端、聊天会话、知识库集合、嵌入器状态

如果 GPU、Ollama 或 Embedding 模型不可用，平台可以显示降级状态；这不代表默认 Docker 体验版失败。只有核心入口或 API 不可访问时，才需要优先排查容器日志。

## 查看日志

```bash
docker compose logs -f api
docker compose logs -f frontend
docker compose logs -f api frontend
```

## 停止服务

```bash
docker compose down
```

停止并删除容器、网络，但保留本地挂载目录和 Docker volume。

## 重建镜像

```bash
docker compose build --no-cache
docker compose up -d
```

## 清理体验数据

本项目默认把数据持久化到仓库目录：

| 宿主机目录 | 容器目录 | 用途 |
| --- | --- | --- |
| `./models` | `/app/models` | 模型文件 |
| `./datasets` | `/app/datasets` | 数据集 |
| `./outputs` | `/app/outputs` | 训练输出和检查点 |
| `./logs` | `/app/logs` | 后端日志 |
| `./data` | `/app/data` | Chat Session、知识库向量数据等运行期数据 |

需要重置体验数据时，先停止容器，再按需删除这些目录中的内容。

Docker 体验版还会把 HuggingFace、Sentence Transformers、ModelScope 缓存指向 `/app/models` 下的子目录，避免容器重建后重复下载常用模型。

```bash
docker compose down
```

## 启动 Ollama 模式

```bash
docker compose --profile ollama up -d --build
```

后端容器内默认使用：

```bash
OLLAMA_BASE_URL=http://ollama:11434
```

浏览器仍通过前端访问平台，不需要直接访问容器内地址。需要拉取 Ollama 模型时，可以执行：

```bash
docker exec -it finetune-ollama ollama pull qwen2.5:0.5b
```

## 启动 GPU 模式

GPU 不是默认体验栈的硬依赖。确认 Docker Desktop、NVIDIA Driver、NVIDIA Container Toolkit 可用后，再叠加 GPU override：

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
```

如果同时需要 Ollama：

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml --profile ollama up -d --build
```

无 GPU 环境下不要使用 `docker-compose.gpu.yml`，否则 Docker 可能因为找不到 NVIDIA runtime 而拒绝启动服务。

## 开发模式前端

默认 Docker 体验版使用生产版前端。如果需要 Vite 开发服务器，可以只启动 `api` 和 `frontend-dev`：

```bash
docker compose --profile dev up -d api frontend-dev
```

注意不要同时启动默认 `frontend` 和 `frontend-dev`，它们都会占用宿主机 `5173` 端口。

## 常见问题

### 前端能打开，但页面提示后端断开

先检查：

```bash
docker compose ps
docker compose logs -f api
python scripts/verify_docker_release.py
```

确认 `http://localhost:8000/health` 可访问，并检查 CORS 配置中包含 `http://localhost:5173`。

### 训练页面提示没有 GPU

默认体验栈允许无 GPU 启动。没有 GPU 时，训练能力应显示明确不可用或降级提示。需要真实 GPU 训练时使用 GPU 模式启动。

### Ollama 不可用

默认体验栈不会启动 Ollama。需要本地 Ollama 能力时使用：

```bash
docker compose --profile ollama up -d
```

然后查看：

```bash
docker compose logs -f ollama
```

### 知识库嵌入器未加载

首次加载 Embedding 模型可能需要下载模型，网络不可用时会显示降级状态。默认体验版要求状态诚实可见，不要求每台机器都能立即完成模型下载。
