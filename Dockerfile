# Finetune Platform Dockerfile
# 大模型微调平台 - Docker 镜像
# 使用 bookworm 明确锁定 Debian 12（Stable），避免 trixie/testing 的包不稳定问题

FROM python:3.11-slim-bookworm

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/app/.venv/bin:$PATH" \
    MODELS_DIR=/app/models \
    DATASETS_DIR=/app/datasets \
    OUTPUTS_DIR=/app/outputs \
    HF_HOME=/app/models/huggingface \
    SENTENCE_TRANSFORMERS_HOME=/app/models/sentence-transformers \
    MODELSCOPE_CACHE_DIR=/app/models/modelscope_cache \
    UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
    UV_EXTRA_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple/

# 设置工作目录
WORKDIR /app

# 安装系统依赖（只装运行时必须的库，不装 build-essential 编译器）
# bookworm 用 deb.debian.org，如遇网络问题可在 Docker Engine DNS 设置中加 114.114.114.114
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libmagic1 \
    libgomp1 \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY pyproject.toml uv.lock ./

# 安装 uv 并同步依赖（使用国内 PyPI 镜像，--no-binary :none: 可换 wheel）
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ uv \
    && uv sync --frozen --no-dev --no-install-project

# 复制服务器代码
COPY server/ ./server/

# 创建必要的目录
RUN mkdir -p /app/models /app/datasets /app/outputs /app/logs /app/data

# 设置环境变量
ENV PYTHONPATH=/app/server
ENV HOST=0.0.0.0
ENV PORT=8010

# 暴露端口
EXPOSE 8010

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8010/health || exit 1

# 启动命令
CMD ["python", "-m", "uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8010"]
