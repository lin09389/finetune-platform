"""
训练模块 Pydantic 模型与类型定义
"""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class TrainingConfigInput(BaseModel):
    """训练配置输入 - 支持高精度微调"""
    model_config = ConfigDict(protected_namespaces=())

    model_id: str = Field(..., description="模型 ID")
    dataset_id: str = Field(..., description="数据集 ID")
    task_goal: Literal["qa_assistant", "structured_extraction"] = Field(
        default="qa_assistant",
        description="应用目标：qa_assistant/structured_extraction",
    )
    method: str = Field(default="qlora", description="微调方法：qlora/lora/full/dora")
    rank: int = Field(default=8, ge=1, le=256, description="LoRA rank")
    alpha: int = Field(default=16, ge=1, description="LoRA alpha")
    learning_rate: float = Field(default=5e-5, gt=0, description="学习率")
    epochs: int = Field(default=3, ge=1, le=100, description="训练轮数")
    batch_size: int = Field(default=1, ge=1, le=32, description="批次大小")
    gradient_accumulation: int = Field(default=16, ge=1, le=128, description="梯度累积步数")
    max_seq_length: int = Field(default=512, ge=64, le=4096, description="最大序列长度")
    warmup_steps: int = Field(default=100, ge=0, description="预热步数")
    save_steps: int = Field(default=500, ge=100, description="保存间隔")
    logging_steps: int = Field(default=10, ge=1, description="日志间隔")
    resume_from_checkpoint: str | None = Field(default=None, description="从 Trainer 检查点恢复（含 optimizer/scheduler 状态）")
    resume_from_adapter: str | None = Field(default=None, description="从 PEFT adapter 检查点恢复（仅 LoRA 权重）")
    quantization: int = Field(default=4, description="量化位数：4/8/none")

    use_dora: bool = Field(default=False, description="是否使用 DoRA 微调")
    lr_scheduler: str = Field(default="cosine", description="学习率调度：cosine/linear/constant")
    warmup_ratio: float = Field(default=0.1, ge=0, le=1, description="预热比例")
    weight_decay: float = Field(default=0.01, ge=0, description="权重衰减")
    label_smoothing: float = Field(default=0.0, ge=0, le=0.5, description="标签平滑")
    gradient_checkpointing: bool = Field(default=True, description="梯度检查点")
    bf16: bool = Field(default=True, description="使用 BF16 混合精度")
    eval_steps: int = Field(default=100, ge=10, description="评估间隔")
    load_best_model: bool = Field(default=True, description="加载最佳模型")
    target_modules: str = Field(default="all", description="目标模块：all/mlp/attn")
    lora_dropout: float = Field(default=0.05, ge=0, le=0.5, description="LoRA Dropout")
    max_grad_norm: float = Field(default=1.0, ge=0, description="梯度裁剪范数")

    early_stopping_patience: int = Field(default=0, ge=0, le=20, description="早停耐心值（0=禁用）")
    early_stopping_threshold: float = Field(default=0.0, ge=0, description="早停阈值")
    metric_for_best_model: str = Field(default="eval_loss", description="最佳模型指标")
    greater_is_better: bool = Field(default=False, description="指标是否越大越好")

    additional_datasets: list[dict[str, Any]] | None = Field(
        default=None,
        description="额外数据集列表，格式：[{'dataset_id': 'xxx', 'weight': 0.3}]"
    )

    memory_preset: str = Field(default="auto", description="显存预设：auto/6gb/8gb/12gb")
    use_flash_attn: bool = Field(default=False, description="使用 Flash Attention")
    deepspeed_stage: int = Field(default=0, description="DeepSpeed ZeRO 阶段：0/1/2/3")
    offload_optimizer: bool = Field(default=False, description="CPU Offload 优化器")

    use_torch_compile: bool = Field(default=False, description="使用 PyTorch 2.0 compile 编译模型")
    torch_compile_mode: str = Field(default="default", description="compile 模式：default/reduce-overhead/max-autotune")
    dataloader_num_workers: int = Field(default=2, ge=0, le=8, description="DataLoader 工作进程数")
    dataloader_pin_memory: bool = Field(default=True, description="DataLoader 固定内存")
    dataloader_persistent_workers: bool = Field(default=True, description="DataLoader 持久化工作进程")
    use_tf32: bool = Field(default=True, description="使用 TF32 加速（Ampere GPU）")

    precision_preset: str = Field(default="balanced", description="精度预设：max/balanced/fast")

    use_lora_plus: bool = Field(default=False, description="使用 LoRA+ 技术（不同学习率）")
    lora_plus_lr_ratio: float = Field(default=16.0, ge=1.0, description="LoRA+ B/A 学习率比例")

    use_galore: bool = Field(default=False, description="使用 GaLore 梯度投影技术")
    galore_rank: int = Field(default=128, ge=16, le=1024, description="GaLore 投影秩")
    galore_update_proj_gap: int = Field(default=50, ge=10, description="GaLore 投影更新间隔")

    output_path: str | None = Field(default=None, description="输出路径（运行时设置）")


class TrainingProgressResponse(BaseModel):
    """训练进度响应"""
    epoch: int
    step: int
    total_steps: int
    loss: float
    lr: float
    vram_used: float
    elapsed_time: float
    eta: float
    status: str
    message: str
    # 扩展观测字段
    grad_norm: float | None = None
    speed: float = 0.0
    samples_per_sec: float = 0.0
    current_phase: str = ""
    phase_durations: dict[str, float] = Field(default_factory=dict)
    retry_count: int = 0
    queue_position: int = 0
    estimated_wait_seconds: float = 0.0


class TrainingRecordResponse(BaseModel):
    """训练记录响应"""
    model_config = ConfigDict(protected_namespaces=())

    id: str
    model_name: str
    dataset_name: str
    base_model_id: str | None = None
    dataset_id: str | None = None
    task_goal: str | None = None
    method: str
    status: str
    start_time: str
    end_time: str | None
    config: dict
    output_path: str
    adapter_path: str | None = None
    checkpoint_path: str | None
    final_loss: float | None = None
    final_lr: float | None = None
    elapsed_time: float | None = None
    total_steps: int | None = None


class ResourceCheckResponse(BaseModel):
    """资源检查响应"""
    passed: bool
    available_vram: float
    required_vram: float
    suggestions: list[str]
    warnings: list[str]
    recommended_config: dict[str, Any]
    device_name: str | None = None


class TrainingPreflightCheck(BaseModel):
    """单项训练预检结果"""
    key: str
    label: str
    status: str = Field(description="passed/warning/blocked")
    message: str
    detail: str | None = None


class TrainingPreflightResponse(BaseModel):
    """训练启动前预检响应"""
    passed: bool
    status: str = Field(description="ready/warning/blocked")
    summary: str
    checks: list[TrainingPreflightCheck] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    recommended_config: dict[str, Any] = Field(default_factory=dict)
    available_vram: float | None = None
    required_vram: float | None = None
    device_name: str | None = None


class SwiftCheckResponse(BaseModel):
    """SWIFT 可用性检查响应"""
    available: bool
    version: str = ""
    message: str = ""


class QueueTaskResponse(BaseModel):
    """队列任务响应"""
    task_id: str
    status: str
    priority: str
    queued_at: str
    message: str


class ValidationResult(BaseModel):
    """训练验证结果"""
    passed: bool = True
    errors: list[str] = []
    warnings: list[str] = []


TrainingProgressStatus = Literal[
    "idle",
    "loading",
    "training",
    "running",
    "stopping",
    "stopped",
    "completed",
    "failed",
]

TRAINING_PROGRESS_STATUS_VALUES: tuple[TrainingProgressStatus, ...] = (
    "idle",
    "loading",
    "training",
    "running",
    "stopping",
    "stopped",
    "completed",
    "failed",
)


SUPPORTED_DATASET_FORMATS = (
    "messages",
    "text",
    "content",
    "instruction+output",
    "instruction+input+output",
)


RELEASE_EXPERIMENTAL_FEATURE_MESSAGES = {
    "use_dora": "DoRA 目前未纳入发布版稳定能力，请使用 LoRA / QLoRA 训练路径",
    "use_lora_plus": "LoRA+ 目前仅保留实验接线，发布版暂不开放",
    "use_galore": "GaLore 当前依赖和兼容性尚未收敛，发布版暂不开放",
}
