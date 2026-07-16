"""
核心配置管理模块
"""
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

HF_MIRRORS = {
    "official": "https://huggingface.co",
    "hf-mirror": "https://hf-mirror.com",
    "aliyun": "https://mirrors.aliyun.com/huggingface",
    "modelscope": "https://modelscope.cn/models",
}


class Settings(BaseSettings):
    """应用配置"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        protected_namespaces=(),
    )

    host: str = Field(default="127.0.0.1", description="服务主机")
    port: int = Field(default=8000, ge=1, le=65535, description="服务端口")
    log_level: str = Field(default="INFO", description="应用日志级别")
    log_format: Literal["text", "json"] = Field(
        default="text",
        description="应用日志格式（LOG_FORMAT）：text 或 json",
    )
    log_max_bytes: int = Field(
        default=10 * 1024 * 1024,
        ge=1024,
        description="日志文件轮转上限字节（LOG_MAX_BYTES），默认 10MB",
    )
    log_backup_count: int = Field(
        default=5,
        ge=1,
        description="轮转备份文件数（LOG_BACKUP_COUNT），默认 5",
    )
    observability_max_series: int = Field(
        default=256,
        ge=16,
        le=4096,
        description="本地 Prometheus 聚合指标允许的最大时间序列数（OBSERVABILITY_MAX_SERIES）",
    )

    environment: Literal["development", "staging", "production"] = Field(
        default="development",
        description="运行环境：development/staging/production"
    )

    enable_auth: bool = Field(
        default=True,
        description="是否启用JWT认证（生产环境强制启用）"
    )

    jwt_secret_key: str | None = Field(
        default=None,
        description="JWT 密钥（生产环境必须设置）"
    )
    jwt_algorithm: str = Field(default="HS256", description="JWT 算法")
    jwt_access_token_expire_minutes: int = Field(default=30, description="Access Token 过期时间（分钟）")
    jwt_refresh_token_expire_days: int = Field(default=7, description="Refresh Token 过期时间（天）")

    allowed_origins: list[str] | str = Field(
        default=["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:3000", "http://127.0.0.1:5173"],
        description="允许的 CORS 来源（生产环境必须限制为具体域名）"
    )

    rate_limit: int = Field(default=100, ge=1, description="速率限制请求数")
    rate_window: int = Field(default=60, ge=1, description="速率限制时间窗口 (秒)")

    base_dir: Path = Field(default=Path(__file__).parent.parent, description="基础目录")
    models_dir: Path | None = Field(default=None, description="模型目录")
    datasets_dir: Path | None = Field(default=None, description="数据集目录")
    outputs_dir: Path | None = Field(default=None, description="输出目录")

    ollama_base_url: str = Field(default="http://localhost:11434", description="Ollama 基础 URL")
    ollama_fast_mode: bool = Field(default=True, description="Ollama 快速模式（更短输出、更低延迟）")
    ollama_fast_max_tokens: int = Field(default=128, ge=16, le=2048, description="快速模式下最大生成 token")
    ollama_timeout_seconds: int = Field(default=60, ge=10, le=600, description="Ollama 请求超时（秒）")
    ollama_stream_read_timeout_seconds: int = Field(default=120, ge=10, le=1200, description="Ollama 流式读取超时（秒）")
    ollama_max_connections: int = Field(default=10, ge=1, le=100, description="Ollama 连接池最大连接数")
    ollama_max_retries: int = Field(default=3, ge=0, le=10, description="Ollama 请求重试次数")
    ollama_retry_delay_seconds: float = Field(default=1.0, ge=0.1, le=10.0, description="Ollama 重试基础延迟（秒）")

    # Ollama 高级性能参数 (为单用户优化)
    ollama_num_ctx: int = Field(default=4096, ge=1024, description="Ollama 上下文窗口大小")
    ollama_num_batch: int = Field(default=1024, ge=1, description="Ollama 处理 prompt 的批次大小")
    ollama_num_thread: int | None = Field(default=None, description="Ollama 使用的 CPU 线程数 (默认自动)")
    ollama_num_gpu: int | None = Field(default=None, description="Ollama 强制使用 GPU 的层数 (默认自动)")

    inference_engine: Literal["huggingface", "vllm", "llamacpp", "ollama"] = Field(
        default="huggingface",
        description="推理引擎类型"
    )

    enable_flash_attention: bool = Field(default=True, description="启用 Flash Attention 加速")

    enable_batching: bool = Field(default=False, description="启用动态批处理")
    max_batch_size: int = Field(default=8, ge=1, le=64, description="最大批处理大小")
    max_batch_wait_ms: int = Field(default=50, ge=0, le=1000, description="批处理最大等待时间 (毫秒)")

    kv_cache_dtype: Literal["float16", "int8", "fp8"] = Field(
        default="float16",
        description="KV Cache 数据类型"
    )
    enable_prefix_caching: bool = Field(default=True, description="启用前缀缓存优化")

    vllm_gpu_memory_utilization: float = Field(
        default=0.9,
        ge=0.1,
        le=1.0,
        description="vLLM GPU 显存利用率"
    )
    vllm_max_model_len: int = Field(default=4096, ge=256, description="vLLM 最大序列长度")
    vllm_tensor_parallel_size: int = Field(default=1, ge=1, le=8, description="vLLM 张量并行大小")

    stream_buffer_size: int = Field(default=10, ge=1, le=100, description="流式输出缓冲区大小")
    stream_flush_interval_ms: int = Field(default=8, ge=1, le=1000, description="流式输出刷新间隔 (毫秒)")
    enable_backpressure: bool = Field(default=True, description="启用背压控制")
    agent_session_langgraph_enabled: bool = Field(default=True, description="是否启用 agent_session LangGraph 主路径")
    agent_session_max_seconds: int = Field(
        default=3600,
        ge=60,
        le=24 * 3600,
        description="单次 Agent prompt/resume 墙钟超时（秒，AGENT_SESSION_MAX_SECONDS），默认 1 小时",
    )
    agent_cloud_model_timeout_seconds: int = Field(default=180, ge=10, le=900, description="Agent 云端模型请求超时（秒）")
    agent_cloud_model_max_retries: int = Field(default=2, ge=0, le=10, description="Agent 云端模型请求最大重试次数")
    langgraph_checkpoint_retention_days: int = Field(
        default=30,
        ge=0,
        description="终态 Agent LangGraph checkpoint 的保留天数（0 表示启动清理时立即过期）",
    )
    langgraph_checkpoint_cleanup_on_startup: bool = Field(
        default=False,
        description="是否在启动时清理超过保留期的终态 Agent LangGraph checkpoint",
    )
    langgraph_checkpoint_vacuum_on_cleanup: bool = Field(
        default=False,
        description="checkpoint 清理后是否 VACUUM 回收磁盘空间（可能耗时并持有独占锁）",
    )
    agent_default_project_path: str | None = Field(
        default=None,
        description="Agent 默认项目路径（本地开发可设为绝对路径；未设置则自动推断到仓库根目录）",
    )
    # Scheme A: DeepAgents tool-result offload / execute capture limits
    agent_execute_max_output_bytes: int = Field(
        default=200_000,
        ge=8_192,
        le=5_000_000,
        description="execute 命令捕获输出上限（字节，AGENT_EXECUTE_MAX_OUTPUT_BYTES）；超出则截断",
    )
    agent_tool_token_limit_before_evict: int = Field(
        default=12_000,
        ge=1_000,
        le=100_000,
        description="工具结果超过该约 token 数时由 DeepAgents 外置到 /large_tool_results/（AGENT_TOOL_TOKEN_LIMIT_BEFORE_EVICT）",
    )
    agent_tool_result_ui_max_chars: int = Field(
        default=12_000,
        ge=2_000,
        le=200_000,
        description="写入时间线 part 的工具结果最大字符数（AGENT_TOOL_RESULT_UI_MAX_CHARS）；全文可在 VFS",
    )

    intent_route_chat_threshold: float = Field(default=0.45, ge=0, le=1, description="意图路由 chat 阈值")
    intent_route_tool_threshold: float = Field(default=0.75, ge=0, le=1, description="意图路由 tool 阈值")
    intent_action_execution_threshold: float = Field(default=0.72, ge=0, le=1, description="意图动作执行阈值")
    intent_llm_timeout_ms: int = Field(default=1500, ge=100, le=15000, description="意图判定 LLM 超时(毫秒)")
    intent_use_bert_classifier: bool = Field(default=False, description="是否启用 BERT 意图分类")

    enable_perf_monitoring: bool = Field(default=True, description="启用性能监控")
    perf_log_interval: int = Field(default=60, ge=10, le=3600, description="性能日志记录间隔 (秒)")
    offline_cache_ttl_seconds: int = Field(default=600, ge=0, description="本地离线缓存 TTL（秒）")
    enable_inference_grpc: bool = Field(default=False, description="启用本地推理 gRPC 服务")
    inference_grpc_host: str = Field(default="127.0.0.1", description="本地推理 gRPC 绑定地址")
    inference_grpc_port: int = Field(default=50061, ge=1, le=65535, description="本地推理 gRPC 端口")
    inference_execution_mode: Literal["service", "in_process"] = Field(
        default="service",
        description="本地推理执行模式：独立服务或兼容的 API 进程内执行",
    )
    inference_service_url: str = Field(default="http://127.0.0.1:8020")
    inference_service_host: str = Field(default="127.0.0.1")
    inference_service_port: int = Field(default=8020, ge=1, le=65535)
    inference_internal_api_key: str = Field(
        default="finetune-local-inference-dev-key",
        description="Internal key shared by control plane and inference_server",
    )
    allow_local_agent_auth: bool = Field(
        default=False,
        description="Explicit opt-in for local agent auth fallback (ALLOW_LOCAL_AGENT_AUTH)",
    )
    sandbox_execution_mode: Literal["local", "wsl"] = Field(
        default="local",
        description=(
            "Agent execute 工具的沙箱模式（SANDBOX_EXECUTION_MODE）："
            "local=本机 cmd/shell 直接执行（默认）；"
            "wsl=在 WSL2 Linux bash 中执行（仅 Windows 生效，提供 Linux 工具链兼容；不是安全边界）"
        ),
    )
    sandbox_wsl_distribution: str | None = Field(
        default=None,
        description=(
            "WSL execute 使用的发行版名称（SANDBOX_WSL_DISTRIBUTION）；"
            "未配置时自动选择首个非 Docker 且可用于 Agent 的发行版"
        ),
    )
    gpu_coordination: bool = Field(
        default=True,
        description="Cross-process GPU train/infer coordination (GPU_COORDINATION)",
    )
    enable_experimental_capabilities: bool = Field(
        default=True,
        description=(
            "Register experimental routers (CUA/MCP/Gateway/Heartbeat/OCR). "
            "Production/staging default OFF unless ENABLE_EXPERIMENTAL_CAPABILITIES "
            "is explicitly true."
        ),
    )
    inference_service_connect_timeout_seconds: float = Field(default=3.0, ge=0.1, le=60)
    inference_service_read_timeout_seconds: float = Field(default=180.0, ge=1, le=3600)
    inference_service_max_retries: int = Field(default=2, ge=0, le=10)
    inference_service_retry_delay_seconds: float = Field(default=0.25, ge=0, le=10)
    inference_cloud_fallback_enabled: bool = Field(default=False)
    inference_cloud_fallback_provider: str | None = Field(default=None)
    inference_cloud_fallback_model: str | None = Field(default=None)

    hf_mirror: str = Field(
        default="hf-mirror",
        description="HuggingFace 镜像源：official/hf-mirror/aliyun/modelscope"
    )

    model_source: Literal["modelscope", "huggingface"] = Field(
        default="modelscope",
        description="模型下载源：modelscope/huggingface"
    )

    modelscope_cache_dir: Path | None = Field(
        default=None,
        description="ModelScope 缓存目录"
    )

    http_proxy: str | None = Field(
        default=None,
        description="HTTP 代理地址，如：http://127.0.0.1:7890"
    )
    https_proxy: str | None = Field(
        default=None,
        description="HTTPS 代理地址，如：http://127.0.0.1:7890"
    )

    max_concurrent_training: int = Field(default=1, ge=1, le=4, description="最大并发训练数")
    enable_checkpoint: bool = Field(default=True, description="启用检查点")
    checkpoint_interval: int = Field(default=500, ge=100, description="检查点间隔步数")
    training_execution_mode: Literal["worker", "in_process"] = Field(
        default="worker",
        description="训练执行模式：独立 GPU Worker 或兼容的 API 进程内执行",
    )
    training_worker_poll_seconds: float = Field(default=1.0, ge=0.1, le=60)
    training_worker_heartbeat_seconds: float = Field(default=5.0, ge=0.5, le=120)
    training_worker_lease_seconds: int = Field(default=30, ge=5, le=3600)
    training_worker_max_attempts: int = Field(default=3, ge=1, le=20)
    training_worker_stale_seconds: int = Field(default=30, ge=5, le=3600)
    # Durable training_events retention (worker / SQLite hub)
    training_events_max_rows: int = Field(
        default=50_000,
        ge=1_000,
        le=1_000_000,
        description="Max training_events rows retained; older rows pruned",
    )
    training_events_max_age_days: int = Field(
        default=14,
        ge=1,
        le=365,
        description="Drop training_events older than this many days",
    )
    training_events_progress_min_step_delta: int = Field(
        default=1,
        ge=1,
        le=1000,
        description="Sample progress_updated events: keep when step advances by at least this",
    )

    max_upload_size: int = Field(default=100 * 1024 * 1024, description="最大上传大小 (字节)")
    allowed_file_types: list[str] | str = Field(
        default=[".json", ".jsonl"],
        description="允许的文件类型"
    )

    @model_validator(mode="after")
    def validate_environment_security(self):
        """Fail-closed security baseline for production/staging (all fields available)."""
        import os

        v = self.environment
        if v in ("production", "staging"):
            if not self.enable_auth:
                raise ValueError(f"{v} 环境必须启用认证 (ENABLE_AUTH=true)")
            if not self.jwt_secret_key:
                raise ValueError(f"{v} 环境必须设置 JWT_SECRET_KEY")
            origins = self.allowed_origins
            if isinstance(origins, list) and "*" in origins:
                raise ValueError(f"{v} 环境不允许 CORS 通配符 (ALLOWED_ORIGINS=*)")
            if self.inference_internal_api_key == "finetune-local-inference-dev-key":
                raise ValueError(
                    f"{v} 环境禁止使用默认 INFERENCE_INTERNAL_API_KEY "
                    "(finetune-local-inference-dev-key)"
                )
            # Production-safe default: experimental off unless explicitly opted in.
            # NOTE: We intentionally read the raw env var here rather than
            # ``self.enable_experimental_capabilities``. The field defaults to True
            # (so dev/test get experimental routes), so we cannot distinguish a
            # deliberate production opt-in from the default by field value alone.
            # In production/staging the env var ENABLE_EXPERIMENTAL_CAPABILITIES
            # is the single source of truth — a value set only via config file
            # will NOT enable experimental routes in production. This is the
            # safe, fail-closed behavior.
            raw_exp = os.environ.get("ENABLE_EXPERIMENTAL_CAPABILITIES")
            if raw_exp is None or str(raw_exp).strip().lower() not in {
                "1",
                "true",
                "yes",
                "on",
            }:
                object.__setattr__(self, "enable_experimental_capabilities", False)
        return self

    @field_validator('allowed_origins', mode='before')
    @classmethod
    def parse_origins(cls, v):
        if isinstance(v, str):
            if v.strip() == "*":
                return ["*"]
            if v.startswith('[') and v.endswith(']'):
                import json
                try:
                    return json.loads(v)
                except (TypeError, json.JSONDecodeError):
                    pass
            return [x.strip() for x in v.split(',') if x.strip()]
        return v

    @field_validator('allowed_file_types', mode='before')
    @classmethod
    def parse_file_types(cls, v):
        if isinstance(v, str):
            if v.startswith('[') and v.endswith(']'):
                import json
                try:
                    return json.loads(v)
                except (TypeError, json.JSONDecodeError):
                    pass
            return [x.strip().lower() for x in v.split(',') if x.strip()]
        return v

    @property
    def models_dir_resolved(self) -> Path:
        return self.models_dir or self.base_dir / "models"

    @property
    def datasets_dir_resolved(self) -> Path:
        return self.datasets_dir or self.base_dir / "datasets"

    @property
    def outputs_dir_resolved(self) -> Path:
        return self.outputs_dir or self.base_dir / "outputs"

    @property
    def modelscope_cache_dir_resolved(self) -> Path:
        return self.modelscope_cache_dir or self.base_dir / "modelscope_cache"

    @property
    def hf_endpoint(self) -> str:
        """获取 HuggingFace 端点 URL"""
        return HF_MIRRORS.get(self.hf_mirror, HF_MIRRORS["hf-mirror"])

    @property
    def inference_backend(self) -> str:
        """推理后端（兼容别名）"""
        return self.inference_engine

    @inference_backend.setter
    def inference_backend(self, value: str):
        """设置推理后端"""
        self.inference_engine = value


settings = Settings()


def get_settings() -> Settings:
    """获取配置实例"""
    return settings
