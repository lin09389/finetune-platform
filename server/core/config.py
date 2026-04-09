"""
核心配置管理模块
"""
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
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
        extra="ignore"
    )

    host: str = Field(default="127.0.0.1", description="服务主机")
    port: int = Field(default=8000, ge=1, le=65535, description="服务端口")

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

    allowed_origins: list[str] = Field(
        default=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000", "http://127.0.0.1:3000"],
        description="允许的 CORS 来源"
    )

    rate_limit: int = Field(default=100, ge=1, description="速率限制请求数")
    rate_window: int = Field(default=60, ge=1, description="速率限制时间窗口 (秒)")

    base_dir: Path = Field(default=Path(__file__).parent.parent, description="基础目录")
    models_dir: Path | None = Field(default=None, description="模型目录")
    datasets_dir: Path | None = Field(default=None, description="数据集目录")
    outputs_dir: Path | None = Field(default=None, description="输出目录")

    ollama_base_url: str = Field(default="http://localhost:11434", description="Ollama 基础 URL")

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
    stream_flush_interval_ms: int = Field(default=16, ge=1, le=1000, description="流式输出刷新间隔 (毫秒)")
    enable_backpressure: bool = Field(default=True, description="启用背压控制")

    enable_perf_monitoring: bool = Field(default=True, description="启用性能监控")
    perf_log_interval: int = Field(default=60, ge=10, le=3600, description="性能日志记录间隔 (秒)")

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

    max_upload_size: int = Field(default=100 * 1024 * 1024, description="最大上传大小 (字节)")
    allowed_file_types: list[str] = Field(
        default=[".json", ".jsonl"],
        description="允许的文件类型"
    )

    @field_validator('environment', mode='after')
    @classmethod
    def validate_environment_security(cls, v, info):
        if v == 'production':
            enable_auth = info.data.get('enable_auth', True)
            if not enable_auth:
                raise ValueError("生产环境必须启用认证 (ENABLE_AUTH=true)")
            jwt_secret = info.data.get('jwt_secret_key')
            if not jwt_secret:
                raise ValueError("生产环境必须设置 JWT_SECRET_KEY")
        return v

    @field_validator('allowed_origins', mode='before')
    @classmethod
    def parse_origins(cls, v):
        if isinstance(v, str):
            return [x.strip() for x in v.split(',') if x.strip()]
        return v

    @field_validator('allowed_file_types', mode='before')
    @classmethod
    def parse_file_types(cls, v):
        if isinstance(v, str):
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
