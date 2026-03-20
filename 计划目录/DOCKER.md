# Docker 部署指南

## 快速开始

### 1. 启动后端服务

```bash
# 仅启动 API 服务
docker compose up -d api
```

### 2. 启动完整栈（包括前端）

```bash
# 开发模式（包含前端热重载）
docker compose --profile dev up -d
```

### 3. 启动完整栈（包括 Ollama）

```bash
# 包含 Ollama 推理服务
docker compose --profile ollama up -d
```

## 配置

### 环境变量

在 `docker-compose.yml` 中配置以下环境变量：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `HOST` | 服务监听地址 | `0.0.0.0` |
| `PORT` | 服务端口 | `8000` |
| `LOG_LEVEL` | 日志级别 | `INFO` |
| `ALLOWED_ORIGINS` | CORS 允许的来源 | `http://localhost:5173` |
| `OLLAMA_BASE_URL` | Ollama 服务地址 | `http://ollama:11434` |
| `MAX_UPLOAD_SIZE` | 最大上传大小 | `104857600` (100MB) |

### 数据卷

| 宿主机路径 | 容器路径 | 说明 |
|-----------|---------|------|
| `./models` | `/app/models` | 模型存储 |
| `./datasets` | `/app/datasets` | 数据集存储 |
| `./outputs` | `/app/outputs` | 训练输出 |
| `./logs` | `/app/logs` | 日志文件 |

## GPU 支持

### NVIDIA GPU

确保已安装 NVIDIA Container Toolkit：

```bash
# 安装 NVIDIA Container Toolkit
sudo apt-get install -y nvidia-container-toolkit

# 重启 Docker
sudo systemctl restart docker
```

验证 GPU 是否可用：

```bash
docker run --rm --gpus all nvidia/cuda:11.0-base nvidia-smi
```

## 常用命令

```bash
# 查看服务状态
docker compose ps

# 查看日志
docker compose logs -f api

# 重启服务
docker compose restart api

# 停止所有服务
docker compose down

# 清理数据卷
docker compose down -v
```

## API 访问

- API 文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/health
- 前端（开发模式）：http://localhost:5173

## 故障排查

### GPU 不可用

```bash
# 检查 NVIDIA 驱动
nvidia-smi

# 检查 Container Toolkit
docker run --rm --gpus all nvidia/cuda:11.0-base nvidia-smi
```

### 内存不足

调整 Docker 内存限制（Mac/Windows）：
1. 打开 Docker Desktop
2. 设置 → Resources → Memory
3. 增加内存分配

### 端口冲突

修改 `docker-compose.yml` 中的端口映射：

```yaml
ports:
  - "8001:8000"  # 将 8000 改为 8001
```
