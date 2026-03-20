"""
训练管理 API - 线程安全版本 + 断点续训支持
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import os
import uuid
import json
import asyncio
import threading
import traceback as tb
from pathlib import Path
from datetime import datetime
from fastapi.responses import StreamingResponse
from concurrent.futures import ThreadPoolExecutor
from fastapi.websockets import WebSocketState
import logging

from core.config import get_settings, Settings
from core.logging import get_logger
from core.training_state import TrainingState, TrainingProgress, TrainingRecord, get_training_state
from core.utils import (
    get_vram_usage,
    cleanup_gpu_memory,
    format_time,
    pre_training_resource_check,
    safe_cleanup_model
)
from core.training_queue import get_training_queue, TaskPriority, TrainingQueue

logger = get_logger(__name__)

router = APIRouter()


# ============================================================================
# P2-1: 训练可视�?- WebSocket 连接管理�?# ============================================================================

class TrainingWebSocketManager:
    """训练 WebSocket 管理�?- 实时推送训练进度（重构版）
    
    修复�?    - P0-3: WebSocket 连接泄漏，添加超时机制和心跳检�?    """
    
    CONNECTION_TIMEOUT = 300
    HEARTBEAT_INTERVAL = 30
    SEND_TIMEOUT = 10
    
    def __init__(self):
        self._connections: Dict[str, List[WebSocket]] = {}
        self._connection_times: Dict[str, Dict[WebSocket, float]] = {}
        self._lock = threading.Lock()
        self._async_lock = asyncio.Lock()
    
    async def connect(self, task_id: str, websocket: WebSocket):
        """连接到指定任务的 WebSocket"""
        await websocket.accept()
        async with self._async_lock:
            if task_id not in self._connections:
                self._connections[task_id] = []
                self._connection_times[task_id] = {}
            self._connections[task_id].append(websocket)
            self._connection_times[task_id][websocket] = asyncio.get_event_loop().time()
            logger.info(f"WebSocket 连接：task_id={task_id}, 连接�?{len(self._connections[task_id])}")
    
    async def disconnect(self, task_id: str, websocket: WebSocket):
        """断开指定任务�?WebSocket 连接"""
        async with self._async_lock:
            if task_id in self._connections:
                try:
                    self._connections[task_id].remove(websocket)
                except ValueError:
                    pass
                
                if task_id in self._connection_times and websocket in self._connection_times[task_id]:
                    del self._connection_times[task_id][websocket]
                
                if not self._connections[task_id]:
                    del self._connections[task_id]
                    if task_id in self._connection_times:
                        del self._connection_times[task_id]
                    logger.info(f"WebSocket 断开：task_id={task_id}")
    
    async def broadcast(self, task_id: str, data: Dict[str, Any]):
        """向指定任务的所有连接广播数�?""
        async with self._async_lock:
            if task_id not in self._connections:
                return
            
            message = json.dumps(data)
            disconnected = []
            current_time = asyncio.get_event_loop().time()
            
            for websocket in list(self._connections[task_id]):
                try:
                    if task_id in self._connection_times:
                        conn_time = self._connection_times[task_id].get(websocket, 0)
                        if current_time - conn_time > self.CONNECTION_TIMEOUT:
                            logger.warning(f"WebSocket 连接超时：task_id={task_id}")
                            disconnected.append(websocket)
                            continue
                    
                    try:
                        await asyncio.wait_for(
                            websocket.send_text(message),
                            timeout=self.SEND_TIMEOUT
                        )
                    except asyncio.TimeoutError:
                        logger.warning(f"WebSocket 发送超时：task_id={task_id}")
                        disconnected.append(websocket)
                        
                except Exception as e:
                    logger.warning(f"WebSocket 发送失败：{e}")
                    disconnected.append(websocket)
            
            for ws in disconnected:
                try:
                    if task_id in self._connections and ws in self._connections[task_id]:
                        self._connections[task_id].remove(ws)
                    if task_id in self._connection_times and ws in self._connection_times[task_id]:
                        del self._connection_times[task_id][ws]
                except Exception:
                    pass
            
            if task_id in self._connections and not self._connections[task_id]:
                del self._connections[task_id]
                if task_id in self._connection_times:
                    del self._connection_times[task_id]
    
    async def broadcast_progress(self, task_id: str, progress: Dict[str, Any]):
        """广播训练进度"""
        await self.broadcast(task_id, {
            "type": "progress",
            "data": progress
        })
    
    async def broadcast_event(self, task_id: str, event_type: str, data: Dict[str, Any]):
        """广播训练事件"""
        await self.broadcast(task_id, {
            "type": "event",
            "event": event_type,
            "data": data
        })
    
    async def cleanup_stale_connections(self):
        """清理超时的连�?""
        async with self._async_lock:
            current_time = asyncio.get_event_loop().time()
            tasks_to_cleanup = []
            
            for task_id, conn_times in list(self._connection_times.items()):
                stale_websockets = [
                    ws for ws, conn_time in conn_times.items()
                    if current_time - conn_time > self.CONNECTION_TIMEOUT
                ]
                
                for ws in stale_websockets:
                    try:
                        if task_id in self._connections and ws in self._connections[task_id]:
                            self._connections[task_id].remove(ws)
                        del conn_times[ws]
                    except Exception:
                        pass
                
                if task_id in self._connections and not self._connections[task_id]:
                    tasks_to_cleanup.append(task_id)
            
            for task_id in tasks_to_cleanup:
                self._connections.pop(task_id, None)
                self._connection_times.pop(task_id, None)


# 全局 WebSocket 管理�?_ws_manager: Optional[TrainingWebSocketManager] = None


def get_ws_manager() -> TrainingWebSocketManager:
    """获取 WebSocket 管理器实�?""
    global _ws_manager
    if _ws_manager is None:
        _ws_manager = TrainingWebSocketManager()
    return _ws_manager


# ============================================================================
# P1-1: 异常恢复机制 - 异常类定�?# ============================================================================

class RecoverableError(Exception):
    """可恢复错�?- 训练失败后可自动重试"""
    pass


class UnrecoverableError(Exception):
    """不可恢复错误 - 需要用户干�?""
    pass


# ============================================================================
# 延迟初始化，�?app 启动时设�?# ============================================================================
_training_state: Optional[TrainingState] = None
_settings: Optional[Settings] = None


def get_state() -> TrainingState:
    """获取训练状态实�?""
    global _training_state
    if _training_state is None:
        settings = get_settings()
        _training_state = get_training_state(settings.outputs_dir_resolved)
    return _training_state


def get_config() -> Settings:
    """获取配置实例"""
    global _settings
    if _settings is None:
        _settings = get_settings()
    return _settings


class TrainingConfigInput(BaseModel):
    """训练配置输入 - 支持高精度微�?""
    model_id: str = Field(..., description="模型 ID")
    dataset_id: str = Field(..., description="数据�?ID")
    method: str = Field(default="qlora", description="微调方法：qlora/lora/full/dora")
    rank: int = Field(default=8, ge=1, le=256, description="LoRA rank")
    alpha: int = Field(default=16, ge=1, description="LoRA alpha")
    learning_rate: float = Field(default=5e-5, gt=0, description="学习�?)
    epochs: int = Field(default=3, ge=1, le=100, description="训练轮数")
    batch_size: int = Field(default=1, ge=1, le=32, description="批次大小")
    gradient_accumulation: int = Field(default=16, ge=1, le=128, description="梯度累积步数")
    max_seq_length: int = Field(default=512, ge=64, le=4096, description="最大序列长�?)
    warmup_steps: int = Field(default=100, ge=0, description="预热步数")
    save_steps: int = Field(default=500, ge=100, description="保存间隔")
    logging_steps: int = Field(default=10, ge=1, description="日志间隔")
    resume_from_checkpoint: Optional[str] = Field(default=None, description="从检查点恢复")
    quantization: int = Field(default=4, description="量化位数�?/8/none")
    
    # P2-3: 高精度微调选项
    use_dora: bool = Field(default=False, description="是否使用 DoRA 微调")
    lr_scheduler: str = Field(default="cosine", description="学习率调度：cosine/linear/constant")
    warmup_ratio: float = Field(default=0.1, ge=0, le=1, description="预热比例")
    weight_decay: float = Field(default=0.01, ge=0, description="权重衰减")
    label_smoothing: float = Field(default=0.0, ge=0, le=0.5, description="标签平滑")
    gradient_checkpointing: bool = Field(default=True, description="梯度检查点")
    bf16: bool = Field(default=True, description="使用 BF16 混合精度")
    eval_steps: int = Field(default=100, ge=10, description="评估间隔")
    load_best_model: bool = Field(default=True, description="加载最佳模�?)
    target_modules: str = Field(default="all", description="目标模块：all/mlp/attn")
    lora_dropout: float = Field(default=0.05, ge=0, le=0.5, description="LoRA Dropout")
    max_grad_norm: float = Field(default=1.0, ge=0, description="梯度裁剪范数")

    # 优化 2: 早停配置
    early_stopping_patience: int = Field(default=0, ge=0, le=20, description="早停耐心值（0=禁用�?)
    early_stopping_threshold: float = Field(default=0.0, ge=0, description="早停阈�?)
    metric_for_best_model: str = Field(default="eval_loss", description="最佳模型指�?)
    greater_is_better: bool = Field(default=False, description="指标是否越大越好")

    # 优化 3: 多数据集支持
    additional_datasets: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="额外数据集列表，格式：[{'dataset_id': 'xxx', 'weight': 0.3}]"
    )

    # P2-4: 低显存优化选项
    memory_preset: str = Field(default="auto", description="显存预设：auto/6gb/8gb/12gb")
    use_flash_attn: bool = Field(default=False, description="使用 Flash Attention")
    deepspeed_stage: int = Field(default=0, description="DeepSpeed ZeRO 阶段�?/1/2/3")
    offload_optimizer: bool = Field(default=False, description="CPU Offload 优化�?)

    # 优化: 训练性能提升选项
    use_torch_compile: bool = Field(default=False, description="使用 PyTorch 2.0 compile 编译模型")
    torch_compile_mode: str = Field(default="default", description="compile 模式：default/reduce-overhead/max-autotune")
    dataloader_num_workers: int = Field(default=2, ge=0, le=8, description="DataLoader 工作进程�?)
    dataloader_pin_memory: bool = Field(default=True, description="DataLoader 固定内存")
    dataloader_persistent_workers: bool = Field(default=True, description="DataLoader 持久化工作进�?)
    use_tf32: bool = Field(default=True, description="使用 TF32 加速（Ampere GPU�?)

    # 预设配置
    precision_preset: str = Field(default="balanced", description="精度预设：max/balanced/fast")

    # P2-5: LoRA+ 配置 (论文: LoRA+)
    use_lora_plus: bool = Field(default=False, description="使用 LoRA+ 技术（不同学习率）")
    lora_plus_lr_ratio: float = Field(default=16.0, ge=1.0, description="LoRA+ B/A 学习率比�?)

    # P2-5: GaLore 配置 (论文: GaLore)
    use_galore: bool = Field(default=False, description="使用 GaLore 梯度投影技�?)
    galore_rank: int = Field(default=128, ge=16, le=1024, description="GaLore 投影�?)
    galore_update_proj_gap: int = Field(default=50, ge=10, description="GaLore 投影更新间隔")

    # 内部使用字段（运行时设置�?    output_path: Optional[str] = Field(default=None, description="输出路径（运行时设置�?)


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


class TrainingRecordResponse(BaseModel):
    """训练记录响应"""
    id: str
    model_name: str
    dataset_name: str
    method: str
    status: str
    start_time: str
    end_time: Optional[str]
    config: dict
    output_path: str
    checkpoint_path: Optional[str]


class ResourceCheckResponse(BaseModel):
    """资源检查响�?""
    passed: bool
    available_vram: float
    required_vram: float
    suggestions: List[str]
    warnings: List[str]
    recommended_config: Dict[str, Any]
    device_name: Optional[str] = None


def load_model_and_tokenizer(
    model_path: str,
    method: str,
    quantize: int = 4,
    resume_from: Optional[str] = None,
    rank: int = 8,
    alpha: int = 16,
    lora_dropout: float = 0.05,
    target_modules: str = "all",
    use_dora: bool = False,
    use_flash_attn: bool = False,
    deepspeed_config: Optional[Dict[str, Any]] = None,
    use_lora_plus: bool = False,
    lora_plus_lr_ratio: float = 16.0
):
    """加载模型和分词器

    Args:
        model_path: 模型路径
        method: 微调方法 (lora/qlora/full/dora)
        quantize: 量化位数 (4/8/0)
        resume_from: 从检查点恢复的路�?        rank: LoRA rank
        alpha: LoRA alpha
        lora_dropout: LoRA dropout
        target_modules: 目标模块 (all/attn/mlp/自定�?
        use_dora: 是否使用 DoRA
        use_flash_attn: 是否使用 Flash Attention
        deepspeed_config: DeepSpeed 配置字典
        use_lora_plus: 是否使用 LoRA+ (论文: LoRA+)
        lora_plus_lr_ratio: LoRA+ B/A 学习率比�?    """
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM
    from peft import LoraConfig, get_peft_model, TaskType, PeftModel, AdaLoraConfig, LoRAConfig as PeftLoRAConfig

    logger.info(f"加载模型：{model_path}, 方法：{method}, 量化：{quantize}, rank={rank}, alpha={alpha}, flash_attn={use_flash_attn}")

    model = None
    tokenizer = None

    try:
        # 量化配置 - 只在 QLoRA 时导�?bitsandbytes
        quantization_config = None
        if method == "qlora" and quantize in [4, 8]:
            try:
                from bitsandbytes import BitsAndBytesConfig
                quantization_config = BitsAndBytesConfig(
                    load_in_4bit=(quantize == 4),
                    load_in_8bit=(quantize == 8),
                    bnb_4bit_compute_dtype=torch.float16,
                    bnb_4bit_use_double_quant=True,
                    bnb_4bit_quant_type="nf4",
                )
            except Exception as e:
                logger.warning(f"bitsandbytes 不可用，将使用标�?LoRA: {e}")
                # 回退到标�?LoRA
                method = "lora"

        # 加载基础模型
        # 尝试使用 Flash Attention (如果可用)
        attn_implementation = "flash_attention_2" if use_flash_attn else "eager"

        load_kwargs = {
            "pretrained_model_name_or_path": model_path,
            "quantization_config": quantization_config,
            "device_map": "auto",
            "torch_dtype": torch.float16,
            "trust_remote_code": True,
        }

        # 只有在不使用量化时才能使�?flash_attention_2
        if use_flash_attn and quantize == 0:
            try:
                load_kwargs["attn_implementation"] = "flash_attention_2"
                model = AutoModelForCausalLM.from_pretrained(**load_kwargs)
                logger.info("已启�?Flash Attention 2")
            except Exception as e:
                logger.warning(f"Flash Attention 2 不可用，回退到标�?attention: {e}")
                load_kwargs["attn_implementation"] = "eager"
                model = AutoModelForCausalLM.from_pretrained(**load_kwargs)
        else:
            if use_flash_attn and quantize > 0:
                logger.warning("量化模式下无法使�?Flash Attention 2，回退到标�?attention")
            model = AutoModelForCausalLM.from_pretrained(**load_kwargs)

        tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)

        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        # 根据 target_modules 配置选择目标模块
        if target_modules == "all":
            target_modules_list = ["q_proj", "v_proj", "k_proj", "o_proj",
                                   "gate_proj", "up_proj", "down_proj"]
        elif target_modules == "attn":
            target_modules_list = ["q_proj", "v_proj", "k_proj", "o_proj"]
        elif target_modules == "mlp":
            target_modules_list = ["gate_proj", "up_proj", "down_proj"]
        else:
            # 自定义模块列表（逗号分隔�?            target_modules_list = [m.strip() for m in target_modules.split(",")]

        # 根据方法选择配置类型
        if use_dora:
            # DoRA 配置
            lora_config = LoraConfig(
                task_type=TaskType.CAUSAL_LM,
                r=rank,
                lora_alpha=alpha,
                lora_dropout=lora_dropout,
                target_modules=target_modules_list,
                bias="none",
                inference_mode=False,
            )
        elif method == "full":
            # 全参数微调，不需�?LoRA
            logger.info("全参数微调模式，不应�?LoRA")
            return model, tokenizer
        else:
            # 标准 LoRA/QLoRA 配置
            lora_config = LoraConfig(
                task_type=TaskType.CAUSAL_LM,
                r=rank,
                lora_alpha=alpha,
                lora_dropout=lora_dropout,
                target_modules=target_modules_list,
                bias="none",
                inference_mode=False,
            )

        # 如果从检查点恢复，直接加�?PEFT 模型，不�?merge
        if resume_from and os.path.exists(resume_from):
            logger.info(f"从检查点恢复：{resume_from}")
            # 直接加载为可训练�?PEFT 模型
            model = PeftModel.from_pretrained(model, resume_from, is_trainable=True)
        else:
            # 新建 LoRA 配置
            model = get_peft_model(model, lora_config)

        # P2-5: LoRA+ 配置 (论文: LoRA+)
        # LoRA+ 的核心是�?LoRA �?A �?B 矩阵设置不同的学习率
        # A 矩阵使用较大的学习率，B 矩阵使用较小的学习率
        if use_lora_plus and method not in ["full"]:
            logger.info(f"应用 LoRA+ 配置: lr_ratio={lora_plus_lr_ratio}")
            for name, param in model.named_parameters():
                if "lora_B" in name:
                    # B 矩阵使用较小的学习率
                    param.requires_grad = True
                elif "lora_A" in name:
                    # A 矩阵保持默认
                    param.requires_grad = True

        return model, tokenizer

    except Exception as e:
        # 清理已分配的资源
        logger.error(f"模型加载失败：{e}")
        if model is not None:
            del model
        if tokenizer is not None:
            del tokenizer
        cleanup_gpu_memory()
        raise


def load_dataset(dataset_path: str, tokenizer, max_length: int = 512):
    """加载数据�?- 支持多种格式"""
    from datasets import Dataset
    import json

    logger.info(f"加载数据集：{dataset_path}")

    def format_conversation(example):
        """支持多种数据格式�?        1. messages 格式 (ChatML): [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
        2. instruction 格式 (Alpaca): {"instruction": "...", "input": "...", "output": "..."}
        3. 纯文本格�? {"text": "..."}
        4. content 格式: {"content": "..."}

        注意：优先使�?chat_template 进行格式化，与推理保持一�?        """
        # 1. messages 格式 (ChatML)
        if "messages" in example:
            messages = example.get("messages", [])

            # 尝试使用 chat_template
            if hasattr(tokenizer, 'apply_chat_template') and messages:
                try:
                    # 使用分词器的 chat_template
                    text = tokenizer.apply_chat_template(
                        messages,
                        tokenize=False,
                        add_generation_prompt=False
                    )
                    return {"text": text}
                except Exception as e:
                    logger.warning(f"chat_template 应用失败，使用简单格式化: {e}")

            # 回退到简单格式化
            text = ""
            for msg in messages:
                role = msg.get("role", "")
                content = msg.get("content", "")
                if role == "user":
                    text += f"User: {content}\n"
                elif role == "assistant":
                    text += f"Assistant: {content}\n"
                elif role == "system":
                    text += f"System: {content}\n"
            return {"text": text}

        # 2. instruction 格式 (Alpaca)
        elif "instruction" in example:
            instruction = example.get("instruction", "")
            input_text = example.get("input", "")
            output = example.get("output", "")
            if input_text:
                text = f"Instruction: {instruction}\nInput: {input_text}\nResponse: {output}"
            else:
                text = f"Instruction: {instruction}\nResponse: {output}"
            return {"text": text}

        # 3. content 格式
        elif "content" in example:
            return {"text": example.get("content", "")}

        # 4. 纯文本格�?        elif "text" in example:
            return {"text": example.get("text", "")}

        # 不支持的格式
        else:
            raise ValueError(f"不支持的数据格式: {example.keys()}")

    # 读取数据
    if dataset_path.endswith(".jsonl"):
        data = []
        with open(dataset_path, "r", encoding="utf-8") as f:
            for line in f:
                data.append(json.loads(line))
    else:
        with open(dataset_path, "r", encoding="utf-8") as f:
            data = json.load(f)

    dataset = Dataset.from_list(data)
    dataset = dataset.map(format_conversation)

    # 分词
    def tokenize_function(examples):
        return tokenizer(
            examples["text"],
            truncation=True,
            max_length=max_length,
            padding="max_length",
        )

    # 分词后移除所有不需要的列，只保留模型需要的�?    original_columns = dataset.column_names
    dataset = dataset.map(tokenize_function, batched=True)
    # 移除所有原始列，只保留分词后的�?    columns_to_remove = [col for col in original_columns if col != 'input_ids' and col != 'attention_mask' and col != 'labels']
    dataset = dataset.remove_columns(columns_to_remove)

    # 为因果语言模型训练设置 labels（复�?input_ids�?    def set_labels(examples):
        examples["labels"] = examples["input_ids"].copy()
        return examples

    dataset = dataset.map(set_labels, batched=True)
    dataset = dataset.train_test_split(test_size=0.1)

    logger.info(f"数据集大小：训练={len(dataset['train'])}, 测试={len(dataset.get('test', []))}")
    return dataset


def load_multiple_datasets(
    dataset_path: str,
    additional_datasets: List[Dict[str, Any]],
    tokenizer,
    max_length: int = 512,
    settings = None
):
    """优化 3: 加载多个数据集并进行混合训练

    Args:
        dataset_path: 主数据集路径
        additional_datasets: 额外数据集列�?[{"dataset_id": "xxx", "weight": 0.3}, ...]
        tokenizer: 分词�?        max_length: 最大序列长�?        settings: 配置对象

    Returns:
        混合后的数据�?    """
    from datasets import Dataset, interleave_datasets
    import random

    logger.info(f"加载主数据集：{dataset_path}")

    # 加载主数据集
    main_dataset = load_dataset(dataset_path, tokenizer, max_length)
    main_train = main_dataset["train"]

    # 如果没有额外数据集，直接返回
    if not additional_datasets:
        return main_dataset

    # 计算权重
    weights = [1.0]  # 主数据集权重�?1
    dataset_list = [main_train]

    for ds_config in additional_datasets:
        ds_id = ds_config.get("dataset_id")
        weight = ds_config.get("weight", 1.0)

        # 查找数据集文�?        ds_path = None
        if settings:
            ds_dir = settings.datasets_dir_resolved / ds_id
            for ext in [".json", ".jsonl"]:
                for f in ds_dir.glob(f"*{ext}"):
                    ds_path = str(f)
                    break
                if ds_path:
                    break

        if ds_path and os.path.exists(ds_path):
            logger.info(f"加载额外数据集：{ds_id}, weight={weight}")
            ds = load_dataset(ds_path, tokenizer, max_length)
            dataset_list.append(ds["train"])
            weights.append(weight)
        else:
            logger.warning(f"数据集不存在，跳过：{ds_id}")

    if len(dataset_list) == 1:
        return main_dataset

    # 归一化权�?    total_weight = sum(weights)
    normalized_weights = [w / total_weight for w in weights]

    logger.info(f"混合数据集：{len(dataset_list)} 个，权重={normalized_weights}")

    # 交错混合数据�?    interleaved = interleave_datasets(
        dataset_list,
        probabilities=normalized_weights,
        seed=42
    )

    # 重新划分训练/测试�?    interleaved = interleaved.train_test_split(test_size=0.1)

    logger.info(f"混合数据集大小：训练={len(interleaved['train'])}, 测试={len(interleaved.get('test', []))}")
    return interleaved


class ProgressCallback:
    """训练进度回调 - 线程安全版本 + 异步检查点保存"""

    def __init__(
        self,
        total_steps: int,
        start_time: datetime,
        state: TrainingState,
        record: TrainingRecord,
        config: TrainingConfigInput,
        model=None,
        tokenizer=None,
        trainer=None,
        train_logger=None  # P1-3: 训练日志记录�?    ):
        self.total_steps = total_steps
        self.start_time = start_time
        self.state = state
        self.record = record
        self.config = config
        self.current_step = 0
        self.current_epoch = 0
        self.current_loss = 0.0
        self.last_checkpoint_step = 0
        self.model = model
        self.tokenizer = tokenizer
        self.trainer = trainer
        self.train_logger = train_logger  # P1-3

        # P0-1: 异步检查点保存 - 后台线程�?        self._checkpoint_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="checkpoint_saver")
        self._pending_checkpoint = None

        # P0-3: 进度更新频率优化 - 降低更新频率
        self.last_update_step = -1
        self.update_interval = max(1, config.logging_steps)  # �?logging_steps 步更新一�?
        # 优化 4: 滑动窗口 ETA 计算
        self._eta_window_size = 10  # 滑动窗口大小
        self._eta_history = []  # 记录每步的时�?        self._last_eta_time = datetime.now()
        self._steps_per_second = 0.0

        # 获取主事件循环引用（用于 WebSocket 推送）
        try:
            self._event_loop = asyncio.get_running_loop()
        except RuntimeError:
            self._event_loop = None

    def set_trainer(self, trainer):
        """设置 trainer 引用（用于检查点保存�?""
        self.trainer = trainer

    def on_train_begin(self, args, state, control, **kwargs):
        """训练开始时的回�?""
        logger.info(f"训练开始：总步�?{self.total_steps}")
        self.state.queue_progress_update(
            epoch=0, step=0, total_steps=self.total_steps, loss=0.0, lr=0.0,
            vram_used=get_vram_usage(), elapsed_time=0.0, eta=0.0,
            status="training", message="Training started"
        )

    def on_init_end(self, args, state, control, **kwargs):
        """Trainer 初始化结束时的回�?""
        logger.debug("Trainer 初始化完�?)

    def on_epoch_begin(self, args, state, control, **kwargs):
        """每个 epoch 开始时的回�?""
        pass  # 不需要特殊处�?
    def on_epoch_end(self, args, state, control, **kwargs):
        """每个 epoch 结束时的回调"""
        pass  # 不需要特殊处�?
    def on_log(self, args, state, control, **kwargs):
        """日志回调"""
        pass  # 不需要特殊处�?
    def on_step_begin(self, args, state, control, **kwargs):
        """每一步开始时的回�?""
        pass  # 不需要特殊处�?
    def on_prediction_step(self, args, state, control, **kwargs):
        """预测步骤回调"""
        pass  # 不需要特殊处�?
    def on_substep_end(self, args, state, control, **kwargs):
        """子步骤结束回调（梯度累积�?""
        pass  # 不需要特殊处�?
    def on_pre_optimizer_step(self, args, state, control, **kwargs):
        """优化器步骤前回调"""
        pass  # 不需要特殊处�?
    def on_optimizer_step(self, args, state, control, **kwargs):
        """优化器步骤回�?""
        pass  # 不需要特殊处�?
    def on_save(self, args, state, control, **kwargs):
        """保存回调"""
        pass  # 不需要特殊处�?
    def on_evaluate(self, args, state, control, **kwargs):
        """评估回调"""
        pass  # 不需要特殊处�?
    def on_predict(self, args, state, control, metrics, **kwargs):
        """预测回调"""
        pass  # 不需要特殊处�?
    def on_push_begin(self, args, state, control, **kwargs):
        """模型推送到 Hub 前的回调"""
        logger.info("准备推送模型到 Hub")

    def on_step_end(self, args, state, control, **kwargs):
        """每一步结束时的回�?- 优化版：降低更新频率 + 异步检查点"""
        self.current_step = state.global_step
        self.current_epoch = state.epoch

        loss = kwargs.get("loss", 0.0)
        self.current_loss = float(loss) if loss > 0 else 0.0
        
        # P0-3: 降低进度更新频率（每 N 步更新一次，减少 CPU 占用�?        if (self.current_step - self.last_update_step) >= self.update_interval:
            self._update_progress(state, args, kwargs)
            self.last_update_step = self.current_step

        # P0-1: 异步保存检查点（不阻塞训练�?        if (
            self.config.resume_from_checkpoint is None and
            self.current_step % self.config.save_steps == 0 and
            self.current_step > self.last_checkpoint_step
        ):
            self._save_checkpoint_async()
            self.last_checkpoint_step = self.current_step

    def _update_progress(self, state, args, kwargs):
        """实际更新进度的逻辑"""
        elapsed = (datetime.now() - self.start_time).total_seconds()

        # 优化 4: 使用滑动窗口计算更准确的 ETA
        now = datetime.now()
        time_delta = (now - self._last_eta_time).total_seconds()

        if time_delta > 0:
            steps_delta = self.current_step - (self._eta_history[-1]["step"] if self._eta_history else 0)
            if steps_delta > 0:
                self._steps_per_second = steps_delta / time_delta
                self._eta_history.append({
                    "step": self.current_step,
                    "time": now,
                    "steps_per_second": self._steps_per_second
                })

                # 保持滑动窗口大小
                if len(self._eta_history) > self._eta_window_size:
                    self._eta_history.pop(0)

        self._last_eta_time = now

        # 计算 ETA（使用滑动窗口平均）
        if self.current_step > 0 and self._steps_per_second > 0:
            # 使用滑动窗口平均的每秒步�?            avg_steps_per_second = sum(h["steps_per_second"] for h in self._eta_history) / len(self._eta_history) if self._eta_history else self._steps_per_second
            eta = (self.total_steps - self.current_step) / avg_steps_per_second
        else:
            eta = 0

        vram = get_vram_usage()
        lr = getattr(args, "learning_rate", self.config.learning_rate)

        # 使用队列更新进度（无 async 开销�?        self.state.queue_progress_update(
            epoch=int(self.current_epoch) + 1,
            step=self.current_step,
            total_steps=self.total_steps,
            loss=self.current_loss,
            lr=float(lr),
            vram_used=vram,
            elapsed_time=elapsed,
            eta=eta if eta > 0 and eta < 86400 else 0.0,
            status="running",
            message=f"Training epoch {int(self.current_epoch) + 1}/{self.config.epochs}",
        )
        
        # P1-3: 记录指标到文�?        if self.train_logger:
            self.train_logger.log_metrics(
                epoch=int(self.current_epoch) + 1,
                step=self.current_step,
                metrics={
                    "loss": self.current_loss,
                    "lr": float(lr),
                    "vram_used": vram,
                    "elapsed_time": elapsed,
                    "eta": eta
                }
            )
        
        # P2-1: WebSocket 实时推送训练进�?        try:
            ws_manager = get_ws_manager()
            progress_data = {
                "epoch": int(self.current_epoch) + 1,
                "step": self.current_step,
                "total_steps": self.total_steps,
                "loss": self.current_loss,
                "lr": float(lr),
                "vram_used": vram,
                "elapsed_time": elapsed,
                "eta": eta,
                "status": "running",
                "message": f"Training epoch {int(self.current_epoch) + 1}/{self.config.epochs}"
            }
            # 使用 run_coroutine_threadsafe 在主事件循环中调�?            if self._event_loop and not self._event_loop.is_closed():
                asyncio.run_coroutine_threadsafe(
                    ws_manager.broadcast_progress(self.record.id, progress_data),
                    self._event_loop
                )
        except Exception as e:
            logger.debug(f"WebSocket 推送进度失败：{e}")

    def _save_checkpoint_async(self):
        """异步保存检查点 - 后台线程执行，不阻塞训练"""
        logger.info(f"后台保存检查点：step-{self.current_step}")
        
        # 提交到线程池执行
        future = self._checkpoint_executor.submit(self._do_save_checkpoint)
        self._pending_checkpoint = future

    def _do_save_checkpoint(self):
        """实际执行检查点保存（在后台线程运行�?""
        try:
            import torch
            import random
            import numpy as np

            # 优化 4: 检查磁盘空�?            checkpoint_dir = Path(self.record.output_path) / "checkpoints" / f"checkpoint-{self.current_step}"

            # 检查磁盘空�?(需要至�?1GB)
            try:
                import shutil
                disk_usage = shutil.disk_usage(checkpoint_dir)
                free_gb = disk_usage.free / (1024 ** 3)
                if free_gb < 1.0:
                    logger.warning(f"磁盘空间不足 {free_gb:.2f}GB，跳过检查点保存")
                    return
            except Exception as e:
                logger.debug(f"磁盘空间检查失败：{e}")

            checkpoint_dir.mkdir(parents=True, exist_ok=True)

            logger.info(f"保存检查点：{checkpoint_dir}")

            # 1. 保存模型权重
            if self.model is not None:
                model_path = checkpoint_dir / "adapter_model"
                model_path.mkdir(parents=True, exist_ok=True)
                self.model.save_pretrained(str(model_path))

            # 2. 保存分词�?            if self.tokenizer is not None:
                tokenizer_path = checkpoint_dir / "tokenizer"
                tokenizer_path.mkdir(parents=True, exist_ok=True)
                self.tokenizer.save_pretrained(str(tokenizer_path))

            # 3. 保存训练状�?            training_state = {
                "global_step": self.current_step,
                "epoch": float(self.current_epoch),
                "loss": self.current_loss,
                "config": self.config.model_dump(),
            }
            with open(checkpoint_dir / "training_state.json", "w", encoding="utf-8") as f:
                json.dump(training_state, f, indent=2, ensure_ascii=False)

            # 4. 保存优化器和 scheduler 状态（通过 trainer�?            if self.trainer is not None:
                try:
                    optimizer_path = checkpoint_dir / "optimizer.pt"
                    scheduler_path = checkpoint_dir / "scheduler.pt"

                    if self.trainer.optimizer is not None:
                        torch.save(self.trainer.optimizer.state_dict(), optimizer_path)

                    if self.trainer.lr_scheduler is not None:
                        torch.save(self.trainer.lr_scheduler.state_dict(), scheduler_path)

                    logger.debug(f"优化器和 scheduler 状态已保存")
                except Exception as e:
                    logger.warning(f"保存优化器状态失败：{e}")

            # 5. 保存随机种子状态（用于可复现性）
            rng_state = {
                "python": random.getstate(),
                "numpy": np.random.get_state(),
            }
            try:
                if torch.cuda.is_available():
                    rng_state["torch_cuda"] = torch.cuda.get_rng_state().tolist()
            except Exception:
                pass

            with open(checkpoint_dir / "rng_state.json", "w", encoding="utf-8") as f:
                json.dump(rng_state, f, indent=2)

            # 6. 保存适配器配�?            if self.model is not None and hasattr(self.model, 'peft_config'):
                adapter_config = self.model.peft_config.get("default", None)
                if adapter_config:
                    adapter_config.save_pretrained(checkpoint_dir)

            logger.info(f"�?检查点保存完成：{checkpoint_dir}")

            # P1-3: 记录检查点保存到日�?            if self.train_logger:
                self.train_logger.log_checkpoint_saved(
                    step=self.current_step,
                    path=str(checkpoint_dir)
                )

            # 优化 4: 自动清理旧检查点（保持最�?save_total_limit 个）
            self._cleanup_old_checkpoints()

        except Exception as e:
            logger.error(f"保存检查点失败：{e}")
            logger.error(tb.format_exc())
            
            # P1-3: 记录错误
            if self.train_logger:
                self.train_logger.log_error(e, {"step": self.current_step})

    def _cleanup_old_checkpoints(self):
        """优化 4: 自动清理旧检查点，保持最�?save_total_limit �?""
        try:
            checkpoint_base = Path(self.record.output_path) / "checkpoints"
            if not checkpoint_base.exists():
                return

            # 获取所有检查点目录
            checkpoints = sorted(
                [d for d in checkpoint_base.iterdir() if d.is_dir() and d.name.startswith("checkpoint-")],
                key=lambda x: int(x.name.split("-")[1]) if x.name.split("-")[1].isdigit() else 0
            )

            # 保留最新的 save_total_limit �?            max_keep = getattr(self.config, 'save_total_limit', 3)
            if len(checkpoints) > max_keep:
                for old_cp in checkpoints[:-max_keep]:
                    try:
                        import shutil
                        shutil.rmtree(old_cp)
                        logger.info(f"已清理旧检查点：{old_cp.name}")
                    except Exception as e:
                        logger.warning(f"清理检查点失败：{old_cp.name}, {e}")
        except Exception as e:
            logger.debug(f"检查点清理失败：{e}")

    def on_train_end(self, args, state, control, **kwargs):
        """训练结束时的回调 - 等待检查点保存完成"""
        # P0-1: 等待最后的检查点保存完成
        if self._pending_checkpoint:
            logger.info("等待检查点保存完成...")
            try:
                self._pending_checkpoint.result(timeout=300)  # 最多等�?5 分钟
                logger.info("检查点保存完成")
            except Exception as e:
                logger.error(f"等待检查点保存失败：{e}")

        # 关闭线程�?        self._checkpoint_executor.shutdown(wait=False)

        # P1-3: 记录训练完成
        if self.train_logger:
            self.train_logger.log_completion({
                "loss": self.current_loss,
                "elapsed_time": (datetime.now() - self.start_time).total_seconds(),
                "total_steps": self.total_steps
            })
        
        # P2-1: WebSocket 广播训练完成
        try:
            ws_manager = get_ws_manager()
            completion_data = {
                "loss": self.current_loss,
                "elapsed_time": (datetime.now() - self.start_time).total_seconds(),
                "total_steps": self.total_steps
            }
            if self._event_loop and not self._event_loop.is_closed():
                asyncio.run_coroutine_threadsafe(
                    ws_manager.broadcast_event(self.record.id, "training_completed", completion_data),
                    self._event_loop
                )
        except Exception as e:
            logger.debug(f"WebSocket 推送完成事件失败：{e}")

        # 更新进度为完�?        self.state.queue_progress_update(
            epoch=self.config.epochs,
            step=self.total_steps,
            total_steps=self.total_steps,
            loss=0.0,
            lr=0.0,
            vram_used=get_vram_usage(),
            elapsed_time=(datetime.now() - self.start_time).total_seconds(),
            eta=0.0,
            status="completed",
            message="Training completed!",
        )


def training_thread(
    config: TrainingConfigInput,
    model_path: str,
    dataset_path: str,
    state: TrainingState,
    record: TrainingRecord,
    retry_count: int = 0
):
    """
    训练线程 - 使用队列式状态更�?+ P1-1 异常恢复机制

    Args:
        retry_count: 当前重试次数
    """
    import torch
    from transformers import TrainingArguments, Trainer

    # 获取设置
    settings = get_config()

    model = None
    tokenizer = None
    trainer = None

    start_time = datetime.now()
    
    # P1-3: 初始化训练日志记录器
    train_logger = TrainingLogger(record.id, Path(record.output_path))
    train_logger.log_start(config)
    
    logger.info(f"开始训练任务：{record.id} (重试次数：{retry_count})")

    try:
        # 更新状态：加载中（使用队列�?        state.queue_training_state(True)
        state.queue_progress_update(
            epoch=0, step=0, total_steps=0, loss=0.0, lr=0.0,
            vram_used=0.0, elapsed_time=0.0, eta=0.0,
            status="loading", message="Loading model..."
        )

        # P1-1: 加载模型 - 捕获可恢复错�?        try:
            model, tokenizer = load_model_and_tokenizer(
                model_path,
                config.method,
                config.quantization,
                config.resume_from_checkpoint,
                rank=config.rank,
                alpha=config.alpha,
                lora_dropout=config.lora_dropout,
                target_modules=config.target_modules,
                use_dora=config.use_dora,
                use_flash_attn=config.use_flash_attn,
                use_lora_plus=config.use_lora_plus,
                lora_plus_lr_ratio=config.lora_plus_lr_ratio
            )
        except torch.cuda.OutOfMemoryError as e:
            raise RecoverableError(f"加载模型�?OOM: {e}")
        except FileNotFoundError as e:
            raise UnrecoverableError(f"模型文件丢失：{e}")
        except Exception as e:
            if "CUDA" in str(e) or "memory" in str(e).lower():
                raise RecoverableError(f"GPU 错误：{e}")
            raise

        # 加载数据集（使用队列�?        state.queue_progress_update(
            epoch=0, step=0, total_steps=0, loss=0.0, lr=0.0,
            vram_used=0.0, elapsed_time=0.0, eta=0.0,
            status="loading", message="Loading dataset..."
        )
        try:
            # 优化 3: 检查是否有多数据集配置
            if config.additional_datasets:
                logger.info(f"使用多数据集混合训练：{len(config.additional_datasets) + 1} 个数据集")
                dataset = load_multiple_datasets(
                    dataset_path,
                    config.additional_datasets,
                    tokenizer,
                    config.max_seq_length,
                    settings
                )
            else:
                dataset = load_dataset(dataset_path, tokenizer, config.max_seq_length)
        except FileNotFoundError as e:
            raise UnrecoverableError(f"数据集文件丢失：{e}")
        except json.JSONDecodeError as e:
            raise UnrecoverableError(f"数据集格式错误：{e}")

        # 计算总步�?        total_steps = (len(dataset["train"]) // config.batch_size) * config.epochs

        # 优化 1: load_best_model �?eval_strategy 兼容性修�?        # �?eval_steps=0 时，必须禁用 load_best_model
        eval_steps = config.eval_steps if config.eval_steps > 0 else None
        eval_strategy = "steps" if eval_steps else "no"

        # 只有�?eval_strategy �?"steps" 时才能启�?load_best_model
        use_best_model = config.load_best_model and eval_strategy == "steps"
        if config.load_best_model and eval_strategy != "steps":
            logger.warning("load_best_model 需�?eval_steps > 0，已自动禁用")

        # 优化 3: warmup_steps �?warmup_ratio 优先级处�?        # warmup_steps 优先�?warmup_ratio
        warmup_steps = config.warmup_steps
        warmup_ratio = None
        if warmup_steps == 0 and config.warmup_ratio > 0:
            # 如果没有设置 warmup_steps，则使用 warmup_ratio
            warmup_ratio = config.warmup_ratio
        logger.info(f"学习率预热配置：warmup_steps={warmup_steps}, warmup_ratio={warmup_ratio}")

        # P2-1: DeepSpeed 配置
        deepspeed_config = None
        if config.deepspeed_stage > 0 and config.method != "qlora":
            # DeepSpeed ZeRO 配置
            deepspeed_config = {
                "fp16": {"enabled": not config.bf16},
                "bf16": {"enabled": config.bf16},
                "zero_optimization": {
                    "stage": config.deepspeed_stage,
                    "offload_optimizer": {"device": "cpu"} if config.offload_optimizer else False,
                    "offload_param": {"device": "cpu"} if config.offload_optimizer and config.deepspeed_stage >= 2 else False,
                },
                "gradient_accumulation_steps": config.gradient_accumulation,
                "gradient_clipping": config.max_grad_norm,
                "steps_per_print": config.logging_steps,
                "train_batch_size": config.batch_size,
                "train_micro_batch_size_per_gpu": config.batch_size,
            }
            logger.info(f"已配�?DeepSpeed ZeRO-{config.deepspeed_stage}, offload={config.offload_optimizer}")
        elif config.deepspeed_stage > 0 and config.method == "qlora":
            logger.warning("QLoRA 模式下不支持 DeepSpeed，将使用标准训练")

        # 训练参数
        output_dir = config.output_path if hasattr(config, 'output_path') else record.output_path
        training_args = TrainingArguments(
            output_dir=output_dir,
            num_train_epochs=config.epochs,
            per_device_train_batch_size=config.batch_size,
            gradient_accumulation_steps=config.gradient_accumulation,
            learning_rate=config.learning_rate,
            max_steps=total_steps,
            warmup_steps=warmup_steps,
            warmup_ratio=warmup_ratio,
            logging_steps=config.logging_steps,
            save_steps=config.save_steps,
            save_total_limit=3,
            load_best_model_at_end=use_best_model,
            evaluation_strategy=eval_strategy,
            eval_steps=eval_steps,
            report_to="none",
            fp16=not config.bf16,
            bf16=config.bf16,
            gradient_checkpointing=config.gradient_checkpointing,
            dataloader_num_workers=config.dataloader_num_workers,
            dataloader_pin_memory=config.dataloader_pin_memory,
            dataloader_persistent_workers=config.dataloader_persistent_workers if config.dataloader_num_workers > 0 else False,
            remove_unused_columns=False,
            save_strategy="steps",
            lr_scheduler_type=config.lr_scheduler,
            weight_decay=config.weight_decay,
            max_grad_norm=config.max_grad_norm,
            label_smoothing_factor=config.label_smoothing if config.label_smoothing > 0 else None,
            optim="adamw_torch",
            ddp_find_unused_parameters=False,
            deepspeed=deepspeed_config,
            # 优化 2: 早停配置
            metric_for_best_model=config.metric_for_best_model,
            greater_is_better=config.greater_is_better,
        )

        # 优化 2: 添加 EarlyStoppingCallback
        early_stopping_callback = None
        if config.early_stopping_patience > 0 and use_best_model:
            from transformers import EarlyStoppingCallback
            early_stopping_callback = EarlyStoppingCallback(
                early_stopping_patience=config.early_stopping_patience,
                early_stopping_threshold=config.early_stopping_threshold
            )
            logger.info(f"已启用早停：patience={config.early_stopping_patience}, threshold={config.early_stopping_threshold}")

        # 创建 Trainer
        callbacks = []
        if early_stopping_callback:
            callbacks.append(early_stopping_callback)

        trainer = Trainer(
            model=model,
            args=training_args,
            train_dataset=dataset["train"],
            eval_dataset=dataset.get("test"),
            processing_class=tokenizer,  # 新版 transformers 使用 processing_class
            callbacks=callbacks,
        )

        # P2-5: LoRA+ 设置不同参数组的学习�?        # LoRA+ 核心: A 矩阵使用较大学习率，B 矩阵使用较小学习�?        # 注意: LoRA+ �?GaLore 不兼容，会被 GaLore 覆盖
        if config.use_lora_plus and config.method not in ["full"] and not config.use_galore:
            logger.info(f"应用 LoRA+ 不同学习率配�? ratio={config.lora_plus_lr_ratio}")
            base_lr = config.learning_rate

            # 获取所�?LoRA 参数
            lora_a_params = []
            lora_b_params = []
            other_params = []

            for name, param in model.named_parameters():
                if param.requires_grad:
                    if "lora_A" in name:
                        lora_a_params.append(param)
                    elif "lora_B" in name:
                        lora_b_params.append(param)
                    else:
                        other_params.append(param)

            # 创建优化器，�?A �?B 设置不同学习�?            from torch.optim import AdamW
            param_groups = [
                # A 矩阵使用较大的学习率 (base_lr * ratio)
                {"params": lora_a_params, "lr": base_lr * config.lora_plus_lr_ratio},
                # B 矩阵使用基础学习�?                {"params": lora_b_params, "lr": base_lr},
                # 其他参数使用基础学习�?                {"params": other_params, "lr": base_lr},
            ]
            trainer.optimizer = AdamW(param_groups, weight_decay=config.weight_decay)
            logger.info(f"LoRA+ 优化器配�? A参数 lr={base_lr * config.lora_plus_lr_ratio}, B参数 lr={base_lr}")

        # P2-5: GaLore 配置 (需要安�?galore-torch)
        # 论文: GaLore - Memory-Efficient LLM Training by Projecting Gradients to Low-Rank Space
        if config.use_galore:
            # 冲突检�?            if config.deepspeed_stage > 0:
                logger.warning("GaLore �?DeepSpeed 不兼容，已自动禁�?DeepSpeed")
                config.deepspeed_stage = 0

            if config.use_lora_plus:
                logger.warning("GaLore �?LoRA+ 同时启用可能存在冲突，建议关�?LoRA+")

            try:
                import galore_torch
                from galore_torch import GaLoreAdamW

                logger.info(f"配置 GaLore: rank={config.galore_rank}, update_gap={config.galore_update_proj_gap}")

                # GaLore 需要识别哪些层需要投�?                # 通常�?attention �?MLP 的权�?                galore_modules = []
                galore_params = []
                for name, param in model.named_parameters():
                    if param.requires_grad and any(x in name for x in ['q_proj', 'k_proj', 'v_proj', 'o_proj', 'gate_proj', 'up_proj', 'down_proj']):
                        galore_params.append(param)

                if len(galore_params) > 0:
                    # 创建 GaLore AdamW 优化�?                    # 只对特定层使�?GaLore 投影
                    non_galore_params = [p for p in model.parameters() if p.requires_grad and p not in galore_params]

                    param_groups = [
                        {"params": galore_params, "rank": config.galore_rank, "update_proj_gap": config.galore_update_proj_gap},
                        {"params": non_galore_params}
                    ]

                    trainer.optimizer = GaLoreAdamW(
                        param_groups,
                        lr=config.learning_rate,
                        weight_decay=config.weight_decay
                    )

                    logger.info(f"GaLore 已启用，投影参数: {len(galore_params)} �?)
                else:
                    logger.warning("未找到可使用 GaLore 的参数，跳过")

            except ImportError as e:
                logger.warning(f"GaLore 未安装，请运�? pip install galore-torch")
                logger.warning(f"将跳�?GaLore 优化，继续使用标准训�? {e}")

        # 优化: 应用 torch.compile 编译模型
        if config.use_torch_compile and hasattr(model, 'forward'):
            try:
                import torch
                if hasattr(torch, 'compile'):
                    logger.info(f"使用 torch.compile 编译模型，模�? {config.torch_compile_mode}")
                    model = torch.compile(model, mode=config.torch_compile_mode)
                    logger.info("torch.compile 编译成功")
                else:
                    logger.warning("PyTorch 版本不支�?torch.compile，需�?PyTorch 2.0+")
            except Exception as e:
                logger.warning(f"torch.compile 编译失败，跳�? {e}")

        # 优化: 启用 TF32 加�?(Ampere GPU)
        if config.use_tf32:
            try:
                import torch
                if torch.cuda.is_available() and hasattr(torch.cuda, 'set_float32_matmul_precision'):
                    # 检查是否为 Ampere 或更新架�?                    device_name = torch.cuda.get_device_name(0).lower()
                    if any(arch in device_name for arch in ['30', '40', 'a10', 'a100', 'a30', 'l40', 'h100']):
                        torch.backends.cuda.matmul.allow_tf32 = True
                        torch.backends.cudnn.allow_tf32 = True
                        logger.info("已启�?TF32 加�?(Ampere+ GPU)")
                    else:
                        logger.info(f"GPU {device_name} 不支�?TF32，跳�?)
            except Exception as e:
                logger.debug(f"TF32 启用失败: {e}")

        # 添加进度回调（传�?model �?tokenizer �?train_logger�?        callback = ProgressCallback(
            total_steps, start_time, state, record, config,
            model=model, tokenizer=tokenizer, trainer=trainer,
            train_logger=train_logger  # P1-3
        )
        trainer.add_callback(callback)

        # 开始训练（使用队列�?        state.queue_progress_update(
            epoch=0, step=0, total_steps=total_steps, loss=0.0, lr=0.0,
            vram_used=0.0, elapsed_time=0.0, eta=0.0,
            status="training", message="Starting training..."
        )

        # P1-1: 训练过程 - 捕获可恢复错�?        try:
            trainer.train()
        except torch.cuda.OutOfMemoryError as e:
            raise RecoverableError(f"训练�?OOM: {e}")
        except KeyboardInterrupt:
            # 用户中断，不重试
            raise UnrecoverableError("用户中断训练")
        except Exception as e:
            if "CUDA" in str(e) or "memory" in str(e).lower() or "NCCL" in str(e):
                raise RecoverableError(f"GPU 错误：{e}")
            raise

        # 训练完成回调
        callback.on_train_end(None, None, None)

        # 保存最终模�?        output_dir = Path(record.output_path)
        lora_path = output_dir / "lora_adapter"
        lora_path.mkdir(parents=True, exist_ok=True)
        model.save_pretrained(lora_path)
        tokenizer.save_pretrained(lora_path)
        logger.info(f"模型已保存到：{lora_path}")

        # 更新记录
        record.status = "completed"
        record.end_time = datetime.now().isoformat()
        record.checkpoint_path = str(lora_path)

        # 保存历史记录到文件（同步方式，追�?更新记录�?        state.add_to_history_sync(record)
        logger.info(f"训练历史已保存：{record.id}")

    except RecoverableError as e:
        # P1-1: 可恢复错�?- 自动重试
        logger.warning(f"可恢复错误：{e}")
        
        max_retries = 2
        if retry_count < max_retries:
            # 清理资源
            cleanup_gpu_memory(aggressive=True)
            if model is not None:
                safe_cleanup_model(model)
            del model, tokenizer, trainer
            import gc
            gc.collect()
            
            # 智能降级配置
            degraded_config = _degrade_training_config(config)
            logger.info(f"应用降级配置：batch_size={degraded_config.batch_size}, "
                       f"gradient_accumulation={degraded_config.gradient_accumulation}")
            
            # 等待冷却
            cooldown = 30 * (retry_count + 1)
            logger.info(f"等待 {cooldown} 秒后重试...")
            import time
            time.sleep(cooldown)
            
            # 重试
            logger.info(f"�?{retry_count + 1} 次重�?..")
            return training_thread(
                degraded_config, model_path, dataset_path, state, record,
                retry_count + 1
            )
        else:
            logger.error(f"重试次数耗尽 ({max_retries}�?，训练失�?)
            _handle_training_failure(state, record, e, train_logger)

    except UnrecoverableError as e:
        # P1-1: 不可恢复错误 - 直接失败
        logger.error(f"不可恢复错误：{e}")
        _handle_training_failure(state, record, e, train_logger)

    except Exception as e:
        # 未知错误
        logger.error(f"训练失败：{e}")
        logger.error(tb.format_exc())
        _handle_training_failure(state, record, e, train_logger)

    finally:
        # 清理资源（如果不是重试）
        if retry_count == 0:
            _cleanup_training_resources(model, tokenizer, trainer)


def _apply_precision_preset(config: TrainingConfigInput) -> TrainingConfigInput:
    """
    P2-3: 应用精度预设配置
    
    预设选项:
    - max: 最高精�?(全参�?DoRA, 余弦退火，早停)
    - balanced: 平衡精度和效�?(高秩 LoRA)
    - fast: 快速训�?(QLoRA)
    """
    cfg = config.model_copy()
    
    if cfg.precision_preset == "max":
        # 最高精度配�?        cfg.method = "full" if not cfg.use_dora else "dora"
        cfg.learning_rate = 1e-5
        cfg.lr_scheduler = "cosine"
        cfg.warmup_ratio = 0.1
        cfg.weight_decay = 0.01
        cfg.label_smoothing = 0.1
        cfg.gradient_checkpointing = True
        cfg.bf16 = True
        cfg.eval_steps = 100
        cfg.load_best_model = True
        cfg.lora_dropout = 0.05
        cfg.max_grad_norm = 1.0
        logger.info("应用最高精度配�?(max)")
        
    elif cfg.precision_preset == "balanced":
        # 平衡配置
        if cfg.use_dora:
            cfg.rank = 64
            cfg.alpha = 128
        else:
            cfg.rank = 32
            cfg.alpha = 64
        cfg.learning_rate = 2e-5 if cfg.use_dora else 3e-5
        cfg.lr_scheduler = "cosine"
        cfg.warmup_ratio = 0.1
        cfg.weight_decay = 0.01
        cfg.gradient_checkpointing = True
        cfg.bf16 = True
        cfg.eval_steps = 100
        cfg.load_best_model = True
        cfg.lora_dropout = 0.05
        logger.info("应用平衡精度配置 (balanced)")
        
    elif cfg.precision_preset == "fast":
        # 快速配�?- 启用所有性能优化
        cfg.method = "qlora"
        cfg.rank = 16
        cfg.alpha = 32
        cfg.learning_rate = 5e-5
        cfg.lr_scheduler = "linear"
        cfg.warmup_ratio = 0.05
        cfg.weight_decay = 0.01
        cfg.gradient_checkpointing = True
        cfg.bf16 = True
        cfg.eval_steps = 200
        cfg.load_best_model = True
        cfg.lora_dropout = 0.1
        # 性能优化
        cfg.use_torch_compile = True
        cfg.torch_compile_mode = "default"
        cfg.dataloader_num_workers = 2
        cfg.dataloader_pin_memory = True
        cfg.dataloader_persistent_workers = True
        cfg.use_tf32 = True
        cfg.use_flash_attn = True
        logger.info("应用快速训练配�?(fast) - 启用所有性能优化")

    # fast 预设默认启用性能优化
    if cfg.precision_preset == "fast":
        cfg.use_torch_compile = True
        cfg.use_tf32 = True

    return cfg


def _apply_memory_preset(config: TrainingConfigInput) -> TrainingConfigInput:
    """
    P2-4: 应用显存预设配置
    
    预设选项:
    - auto: 自动根据显存调整
    - 6gb: 6GB 显存优化 (极致压缩)
    - 8gb: 8GB 显存优化 (平衡)
    - 12gb: 12GB 显存优化 (高性能)
    """
    cfg = config.model_copy()
    
    if cfg.memory_preset == "6gb":
        # 6GB 显存：极致优�?        cfg.gradient_checkpointing = True
        cfg.gradient_accumulation = 16
        cfg.batch_size = 1
        cfg.quantization = 4  # 4bit 量化
        cfg.bf16 = True
        cfg.use_flash_attn = True
        logger.info("应用 6GB 显存优化配置")
        
    elif cfg.memory_preset == "8gb":
        # 8GB 显存：平衡优�?        cfg.gradient_checkpointing = True
        cfg.gradient_accumulation = 8
        cfg.batch_size = 2
        cfg.quantization = 8  # 8bit 量化 (精度更高)
        cfg.bf16 = True
        cfg.use_flash_attn = True
        logger.info("应用 8GB 显存优化配置")
        
    elif cfg.memory_preset == "12gb":
        # 12GB 显存：DeepSpeed ZeRO-2
        cfg.gradient_checkpointing = True
        cfg.gradient_accumulation = 4
        cfg.batch_size = 2
        cfg.quantization = 0  # 不量�?        cfg.bf16 = True
        cfg.use_flash_attn = True
        cfg.deepspeed_stage = 2  # ZeRO-2
        cfg.offload_optimizer = True
        logger.info("应用 12GB 显存优化配置 (DeepSpeed ZeRO-2)")
        
    elif cfg.memory_preset == "auto":
        # 自动根据显存情况调整
        try:
            import torch
            if torch.cuda.is_available():
                total_vram = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
                
                if total_vram <= 6:
                    cfg.memory_preset = "6gb"
                    return _apply_memory_preset(cfg)
                elif total_vram <= 8:
                    cfg.memory_preset = "8gb"
                    return _apply_memory_preset(cfg)
                elif total_vram <= 12:
                    cfg.memory_preset = "12gb"
                    return _apply_memory_preset(cfg)
        except Exception as e:
            logger.debug(f"自动检测显存失败：{e}")
    
    return cfg


def _degrade_training_config(config: TrainingConfigInput) -> TrainingConfigInput:
    """
    P1-1: 智能降级训练配置
    
    根据当前显存情况自动调整参数
    """
    degraded = config.model_copy()
    
    try:
        import torch
        if torch.cuda.is_available():
            available_vram = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
            allocated_vram = torch.cuda.memory_allocated(0) / (1024 ** 3)
            free_vram = available_vram - allocated_vram
            
            # 根据可用显存降级
            if free_vram < 4.0:
                # 激进降�?                if degraded.batch_size > 1:
                    degraded.batch_size = 1
                if degraded.gradient_accumulation > 8:
                    degraded.gradient_accumulation = 8
                if degraded.max_seq_length > 256:
                    degraded.max_seq_length = 256
            elif free_vram < 6.0:
                # 保守降级
                if degraded.batch_size > 2:
                    degraded.batch_size = 2
                if degraded.gradient_accumulation > 16:
                    degraded.gradient_accumulation = 16
    except Exception as e:
        logger.warning(f"降级配置失败：{e}")
    
    return degraded


def _handle_training_failure(state: TrainingState, record: TrainingRecord, error: Exception, train_logger: 'TrainingLogger' = None):
    """P1-1: 处理训练失败"""
    # 更新进度为失败（使用队列�?    state.queue_progress_update(
        epoch=0, step=0, total_steps=0, loss=0.0, lr=0.0,
        vram_used=0.0, elapsed_time=0.0, eta=0.0,
        status="failed", message=f"Error: {str(error)}"
    )

    # 更新记录
    record.status = "failed"
    record.end_time = datetime.now().isoformat()

    # P1-3: 记录错误
    if train_logger:
        train_logger.log_error(error)

    # 保存失败记录到历史文件（同步方式，追�?更新记录�?    state.add_to_history_sync(record)
    logger.info(f"训练失败记录已保存：{record.id}")


def _cleanup_training_resources(model, tokenizer, trainer):
    """P1-1: 清理训练资源"""
    try:
        # 清理（使用队列）
        from core.utils import cleanup_gpu_memory, safe_cleanup_model
        
        cleanup_gpu_memory(aggressive=True)

        # 安全清理模型
        if model is not None:
            safe_cleanup_model(model)

        # 删除大对象引用，帮助 GC
        del model, tokenizer, trainer
        import gc
        gc.collect()
    except Exception as e:
        logger.warning(f"清理资源失败：{e}")


class TrainingLogger:
    """P1-3: 训练日志记录�?""
    
    def __init__(self, task_id: str, output_dir: Path):
        self.task_id = task_id
        self.log_file = output_dir / "training.log"
        self.metrics_file = output_dir / "metrics.jsonl"
        self.events_file = output_dir / "events.jsonl"
        
        # 确保文件存在
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 结构化日�?        self.logger = logging.getLogger(f"training.{task_id}")
        self.logger.setLevel(logging.INFO)
        
        # 避免重复添加 handler
        if not self.logger.handlers:
            handler = logging.FileHandler(self.log_file, encoding='utf-8')
            formatter = logging.Formatter(
                '%(asctime)s | %(levelname)-8s | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
    
    def log_start(self, config: TrainingConfigInput):
        """P1-3: 记录训练开�?""
        self.logger.info("=" * 60)
        self.logger.info("训练开�?)
        self.logger.info("=" * 60)
        self.logger.info(f"任务 ID: {self.task_id}")
        self.logger.info(f"模型：{config.model_id}")
        self.logger.info(f"数据集：{config.dataset_id}")
        self.logger.info(f"方法：{config.method}")
        self.logger.info(f"Rank: {config.rank}, Alpha: {config.alpha}")
        self.logger.info(f"学习率：{config.learning_rate}")
        self.logger.info(f"批次大小：{config.batch_size}")
        self.logger.info(f"梯度累积：{config.gradient_accumulation}")
        self.logger.info(f"序列长度：{config.max_seq_length}")
        self.logger.info(f"训练轮数：{config.epochs}")
        
        # 记录到事件文�?        self._log_event("training_started", {
            "config": config.model_dump()
        })
    
    def log_metrics(self, epoch: int, step: int, metrics: Dict[str, Any]):
        """P1-3: 记录训练指标"""
        metrics_record = {
            "timestamp": datetime.now().isoformat(),
            "epoch": epoch,
            "step": step,
            **metrics
        }
        
        try:
            with open(self.metrics_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(metrics_record, ensure_ascii=False) + '\n')
        except Exception as e:
            self.logger.warning(f"记录指标失败：{e}")
    
    def log_event(self, event_type: str, data: Dict[str, Any]):
        """P1-3: 记录训练事件"""
        self._log_event(event_type, data)
    
    def _log_event(self, event_type: str, data: Dict[str, Any]):
        """P1-3: 内部事件记录"""
        event = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "data": data
        }
        
        try:
            with open(self.events_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(event, ensure_ascii=False) + '\n')
        except Exception as e:
            self.logger.warning(f"记录事件失败：{e}")
    
    def log_error(self, error: Exception, context: Dict[str, Any] = None):
        """P1-3: 记录错误"""
        self.logger.error(f"错误：{error}", exc_info=True)
        self._log_event("error", {
            "error_type": type(error).__name__,
            "error_message": str(error),
            "context": context or {}
        })
    
    def log_checkpoint_saved(self, step: int, path: str):
        """P1-3: 记录检查点保存"""
        self.logger.info(f"检查点保存：step={step}, path={path}")
        self._log_event("checkpoint_saved", {
            "step": step,
            "path": path
        })
    
    def log_completion(self, final_metrics: Dict[str, Any]):
        """P1-3: 记录训练完成"""
        self.logger.info("=" * 60)
        self.logger.info("训练完成")
        self.logger.info("=" * 60)
        self.logger.info(f"最�?Loss: {final_metrics.get('loss', 'N/A')}")
        self.logger.info(f"训练时长：{final_metrics.get('elapsed_time', 'N/A')}")
        
        self._log_event("training_completed", {
            "final_metrics": final_metrics
        })


@router.post("/stop")
async def stop_training():
    """停止训练"""
    state = get_state()

    if not await state.is_training():
        raise HTTPException(status_code=400, detail="No training in progress")

    # 更新状态（使用队列�?    state.queue_training_state(False)
    state.queue_progress_update(
        status="stopped",
        message="Training stopped by user"
    )

    # 更新记录
    record = await state.get_current_record()
    if record:
        record.status = "stopped"
        record.end_time = datetime.now().isoformat()
        await state.add_to_history(record)

    # P0-2: 清理 GPU（增强版�?    cleanup_gpu_memory(aggressive=True)
    import gc
    gc.collect()

    logger.info("训练已停�?)
    return {"message": "Training stopped"}


@router.get("/progress", response_model=TrainingProgressResponse)
async def get_progress():
    """获取训练进度"""
    state = get_state()
    progress = await state.get_progress()
    return TrainingProgressResponse(**progress.model_dump())


@router.get("/progress/stream")
async def progress_stream(
    timeout: int = Query(default=300, ge=30, le=3600, description="连接超时时间（秒�?),
    heartbeat: int = Query(default=30, ge=10, le=120, description="心跳间隔（秒�?)
):
    """SSE 进度�?- 每次进度更新都发送（重构版）
    
    修复�?    - P1-2: 添加连接超时机制和心跳检�?    
    Args:
        timeout: 连接超时时间（秒），默认 300 �?        heartbeat: 心跳间隔（秒），默认 30 �?    """
    import asyncio
    import time

    state = get_state()

    async def event_generator():
        last_step = -1
        last_status = ""
        idle_count = 0
        last_heartbeat = time.time()
        connection_start = time.time()
        last_activity = time.time()

        try:
            while True:
                current_time = time.time()
                
                if current_time - connection_start > timeout:
                    logger.info(f"SSE 连接超时：已运行 {timeout} �?)
                    yield f"event: timeout\ndata: {{\"message\": \"Connection timeout after {timeout}s\"}}\n\n"
                    break
                
                if current_time - last_activity > timeout:
                    logger.warning(f"SSE 连接空闲超时：{current_time - last_activity:.0f} 秒无活动")
                    yield f"event: timeout\ndata: {{\"message\": \"Idle timeout\"}}\n\n"
                    break
                
                progress = await state.get_progress()

                should_send = (
                    progress.step != last_step or
                    progress.status != last_status
                )

                if should_send:
                    yield f"data: {progress.model_dump_json()}\n\n"
                    last_step = progress.step
                    last_status = progress.status
                    last_activity = current_time

                if current_time - last_heartbeat >= heartbeat:
                    yield f"event: heartbeat\ndata: {{\"timestamp\": {current_time}}}\n\n"
                    last_heartbeat = current_time

                if progress.status == "idle":
                    idle_count += 1
                    if idle_count > 3:
                        yield f"data: {progress.model_dump_json()}\n\n"
                        break
                else:
                    idle_count = 0

                if progress.status in ["completed", "failed", "stopped"]:
                    yield f"data: {progress.model_dump_json()}\n\n"
                    break

                await asyncio.sleep(1)
                
        except asyncio.CancelledError:
            logger.info("SSE 连接被客户端取消")
        except Exception as e:
            logger.error(f"SSE 连接错误：{e}")
            yield f"event: error\ndata: {{\"message\": \"{str(e)}\"}}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.get("/history")
async def get_history():
    """获取训练历史"""
    state = get_state()
    records = await state.get_history()
    return [TrainingRecordResponse(**r.model_dump()) for r in records]


# ============================================================================
# P2-1: 训练可视�?- WebSocket 和指�?API
# ============================================================================

@router.websocket("/ws/{task_id}")
async def training_websocket(websocket: WebSocket, task_id: str):
    """P2-1: 训练进度 WebSocket 推�?""
    ws_manager = get_ws_manager()
    
    await ws_manager.connect(task_id, websocket)
    
    try:
        while True:
            # 保持连接，接收客户端心跳
            data = await websocket.receive_text()
            
            # 可选：处理客户端消息（如请求历史数据）
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        await ws_manager.disconnect(task_id, websocket)
    except Exception as e:
        logger.error(f"WebSocket 错误：{e}")
        await ws_manager.disconnect(task_id, websocket)


@router.get("/metrics/{task_id}")
async def get_training_metrics(task_id: str):
    """P2-1: 获取训练指标数据（用于图表展示）"""
    state = get_state()
    settings = get_config()
    
    # 查找任务输出目录
    output_dir = settings.outputs_dir_resolved / f"train_{task_id[:8]}"
    metrics_file = output_dir / "metrics.jsonl"
    
    if not metrics_file.exists():
        # 返回空数�?        return {
            "task_id": task_id,
            "metrics": [],
            "summary": {
                "total_steps": 0,
                "final_loss": 0,
                "elapsed_time": 0
            }
        }
    
    # 读取指标数据
    metrics = []
    try:
        with open(metrics_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    metric = json.loads(line.strip())
                    metrics.append(metric)
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        logger.error(f"读取指标文件失败：{e}")
    
    # 计算汇总信�?    summary = {
        "total_steps": metrics[-1]["step"] if metrics else 0,
        "final_loss": metrics[-1].get("loss", 0) if metrics else 0,
        "elapsed_time": metrics[-1].get("elapsed_time", 0) if metrics else 0
    }
    
    return {
        "task_id": task_id,
        "metrics": metrics,
        "summary": summary
    }


@router.get("/chart-data/{task_id}")
async def get_chart_data(task_id: str):
    """P2-1: 获取图表数据（简化版，直接返回绘图数据）"""
    state = get_state()
    settings = get_config()
    
    output_dir = settings.outputs_dir_resolved / f"train_{task_id[:8]}"
    metrics_file = output_dir / "metrics.jsonl"
    
    if not metrics_file.exists():
        return {
            "loss_chart": {"labels": [], "data": []},
            "lr_chart": {"labels": [], "data": []},
            "vram_chart": {"labels": [], "data": []}
        }
    
    labels = []
    loss_data = []
    lr_data = []
    vram_data = []
    
    try:
        with open(metrics_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    metric = json.loads(line.strip())
                    labels.append(metric.get("step", 0))
                    loss_data.append(metric.get("loss", 0))
                    lr_data.append(metric.get("lr", 0))
                    vram_data.append(metric.get("vram_used", 0))
                except Exception:
                    continue
    except Exception as e:
        logger.error(f"读取图表数据失败：{e}")
    
    return {
        "loss_chart": {
            "labels": labels,
            "data": loss_data,
            "name": "Loss"
        },
        "lr_chart": {
            "labels": labels,
            "data": lr_data,
            "name": "Learning Rate"
        },
        "vram_chart": {
            "labels": labels,
            "data": vram_data,
            "name": "VRAM Usage (GB)"
        }
    }


@router.get("/status")
async def get_status():
    """获取训练状�?""
    state = get_state()
    return await state.get_status()


# ============================================================================
# P2-2: SWIFT 框架集成 - CLI 调用模式
# ============================================================================

class SwiftCheckResponse(BaseModel):
    """SWIFT 可用性检查响�?""
    available: bool
    version: str = ""
    message: str = ""


@router.get("/check-swift", response_model=SwiftCheckResponse)
async def check_swift():
    """P2-2: 检�?SWIFT 框架是否可用"""
    from backends.swift_backend import get_swift_backend
    
    swift_backend = get_swift_backend()
    
    if swift_backend.is_available():
        return SwiftCheckResponse(
            available=True,
            version=swift_backend.get_version(),
            message="SWIFT 框架已安�?
        )
    else:
        return SwiftCheckResponse(
            available=False,
            message="SWIFT 未安装，请运行：pip install ms-swift -U"
        )


@router.post("/start-swift", response_model=TrainingRecordResponse)
async def start_swift_training(
    config: TrainingConfigInput,
):
    """
    P2-2: 使用 SWIFT 框架启动训练

    使用阿里 SWIFT 框架进行高效微调
    支持：LoRA, QLoRA, 全量微调
    """
    from backends.swift_backend import get_swift_backend, SwiftTrainConfig

    state = get_state()
    settings = get_config()

    # 检�?SWIFT 是否可用
    swift_backend = get_swift_backend()
    if not swift_backend.is_available():
        raise HTTPException(
            status_code=503,
            detail="SWIFT 框架未安装，请运行：pip install ms-swift -U"
        )

    # 检查是否已有训练在进行
    if await state.is_training():
        raise HTTPException(status_code=400, detail="Training already in progress")

    # 验证模型
    model_path = settings.models_dir_resolved / config.model_id
    if not model_path.exists():
        raise HTTPException(status_code=404, detail=f"Model not found: {config.model_id}")

    # 验证数据�?    dataset_path = settings.datasets_dir_resolved / config.dataset_id
    if not dataset_path.exists():
        raise HTTPException(status_code=404, detail=f"Dataset not found: {config.dataset_id}")

    # 资源检�?    resource_check = pre_training_resource_check(
        required_vram_gb=4.0 if config.method == "qlora" else 8.0,
        method=config.method,
        model_size=config.model_id
    )
    if not resource_check["passed"]:
        logger.warning(f"资源检查未通过：{resource_check.get('warnings', [])}")
    
    # 创建输出目录
    record_id = str(uuid.uuid4())
    output_path = settings.outputs_dir_resolved / f"train_{record_id[:8]}"
    output_path.mkdir(parents=True, exist_ok=True)
    
    # 创建训练记录
    record = TrainingRecord(
        id=record_id,
        model_name=config.model_id,
        dataset_name=config.dataset_id,
        method=f"swift_{config.method}",
        status="running",
        start_time=datetime.now().isoformat(),
        config=config.model_dump(),
        output_path=str(output_path),
        checkpoint_path=None,
    )
    
    # 构建 SWIFT 配置
    swift_config = SwiftTrainConfig(
        model_id=str(model_path),
        dataset_id=config.dataset_id,
        method=config.method,
        learning_rate=config.learning_rate,
        epochs=config.epochs,
        batch_size=config.batch_size,
        gradient_accumulation=config.gradient_accumulation,
        max_seq_length=config.max_seq_length,
        lora_rank=config.rank,
        lora_alpha=config.alpha,
        lora_dropout=0.05,
        quantization_bit=config.quantization if config.method == "qlora" else 0,
        output_dir=str(output_path),
        save_steps=config.save_steps,
        logging_steps=config.logging_steps,
        warmup_steps=config.warmup_steps,
        warmup_ratio=0.1,
        weight_decay=0.01,
        max_grad_norm=1.0,
        val_size=0.0,
    )
    
    # 启动 SWIFT 训练
    log_dir = output_path / "logs"
    success = swift_backend.start_training(swift_config, log_dir, record_id)
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to start SWIFT training")
    
    # 保存到历�?    await state.add_to_history(record)
    
    # 启动后台监控任务
    asyncio.create_task(_monitor_swift_training(record_id, state, record, swift_backend))
    
    return TrainingRecordResponse(**record.model_dump())


async def _monitor_swift_training(
    task_id: str,
    state: TrainingState,
    record: TrainingRecord,
    swift_backend
):
    """后台监控 SWIFT 训练进度"""
    import time
    
    logger.info(f"开始监�?SWIFT 训练：{task_id}")

    # 更新状态为训练�?    state.queue_training_state(True)
    
    last_status = "running"
    
    while True:
        await asyncio.sleep(3)  # �?3 秒检查一�?        
        # 获取状�?        status = swift_backend.get_training_status()
        current_status = status.get("status", "unknown")
        
        if current_status == "idle" or current_status == "unknown":
            logger.warning("SWIFT 后端状态异�?)
            continue
        
        if current_status == "running":
            # 解析进度
            progress = swift_backend.parse_training_progress()
            
            if progress.get("step", 0) > 0:
                # 更新进度
                state.queue_progress_update(
                    epoch=progress.get("epoch", 0),
                    step=progress.get("step", 0),
                    total_steps=progress.get("total_steps", 0),
                    loss=progress.get("loss", 0.0),
                    lr=progress.get("lr", 0.0),
                    vram_used=get_vram_usage(),
                    elapsed_time=progress.get("elapsed_time", 0.0),
                    eta=0.0,
                    status="running",
                    message=progress.get("message", "SWIFT Training...")
                )
                
                # WebSocket 推�?                try:
                    ws_manager = get_ws_manager()
                    asyncio.create_task(ws_manager.broadcast_progress(task_id, {
                        **progress,
                        "status": "running"
                    }))
                except Exception as e:
                    logger.debug(f"WebSocket 推送失败：{e}")
        
        elif current_status == "completed":
            logger.info(f"SWIFT 训练完成：{task_id}")

            # 更新状�?            state.queue_training_state(False)
            state.queue_progress_update(
                status="completed",
                message="SWIFT Training completed"
            )
            
            # 更新记录
            record.status = "completed"
            record.end_time = datetime.now().isoformat()
            record.checkpoint_path = str(Path(record.output_path) / "adapter_model")
            
            # WebSocket 推送完成事�?            try:
                ws_manager = get_ws_manager()
                asyncio.create_task(ws_manager.broadcast_event(task_id, "training_completed", {
                    "framework": "swift",
                    "output_path": record.output_path
                }))
            except Exception as e:
                logger.debug(f"WebSocket 推送失败：{e}")
            
            # 保存历史
            state.add_to_history_sync(record)
            
            # 清理
            swift_backend.cleanup()
            break
        
        elif current_status == "failed":
            logger.error(f"SWIFT 训练失败：{task_id}, return_code={status.get('return_code')}")
            
            # 获取日志末尾
            log_tail = swift_backend.get_log_tail(20)
            error_msg = "\n".join(log_tail) if log_tail else "Unknown error"

            # 更新状�?            state.queue_training_state(False)
            state.queue_progress_update(
                status="failed",
                message=f"SWIFT Error: {error_msg[:200]}"
            )
            
            # 更新记录
            record.status = "failed"
            record.end_time = datetime.now().isoformat()
            
            # WebSocket 推送失败事�?            try:
                ws_manager = get_ws_manager()
                asyncio.create_task(ws_manager.broadcast_event(task_id, "training_failed", {
                    "framework": "swift",
                    "error": error_msg[:500]
                }))
            except Exception as e:
                logger.debug(f"WebSocket 推送失败：{e}")
            
            # 保存历史
            state.add_to_history_sync(record)
            
            # 清理
            swift_backend.cleanup()
            break
        
        elif current_status == "stopped":
            logger.info(f"SWIFT 训练已停止：{task_id}")
            break
        
        last_status = current_status


@router.post("/swift/stop")
async def stop_swift_training():
    """P2-2: 停止 SWIFT 训练"""
    from backends.swift_backend import get_swift_backend
    
    swift_backend = get_swift_backend()
    status = swift_backend.get_training_status()
    
    if status.get("status") != "running":
        raise HTTPException(status_code=400, detail="No SWIFT training in progress")
    
    success = swift_backend.stop_training()

    if success:
        # 更新状�?        state = get_state()
        state.queue_training_state(False)
        state.queue_progress_update(
            status="stopped",
            message="SWIFT training stopped by user"
        )
        return {"message": "SWIFT training stopped"}
    else:
        raise HTTPException(status_code=500, detail="Failed to stop SWIFT training")


@router.get("/swift/progress")
async def get_swift_progress():
    """P2-2: 获取 SWIFT 训练进度"""
    from backends.swift_backend import get_swift_backend
    
    swift_backend = get_swift_backend()
    status = swift_backend.get_training_status()
    progress = swift_backend.parse_training_progress()
    
    return {
        **status,
        **progress
    }


@router.get("/swift/logs/{task_id}")
async def get_swift_logs(task_id: str, lines: int = Query(default=50, ge=1, le=200)):
    """P2-2: 获取 SWIFT 训练日志（末�?N 行）"""
    from backends.swift_backend import get_swift_backend
    
    swift_backend = get_swift_backend()
    log_lines = swift_backend.get_log_tail(lines)
    
    return {
        "task_id": task_id,
        "lines": log_lines,
        "count": len(log_lines)
    }


@router.get("/checkpoints/{task_id}")
async def get_checkpoints(task_id: str):
    """获取任务的检查点列表"""
    state = get_state()
    settings = get_config()
    
    # 查找任务输出目录
    output_dir = settings.outputs_dir_resolved / f"train_{task_id[:8]}"
    checkpoint_dir = output_dir / "checkpoints"
    
    if not checkpoint_dir.exists():
        return []
    
    checkpoints = []
    for cp in checkpoint_dir.iterdir():
        if cp.is_dir() and cp.name.startswith("checkpoint-"):
            checkpoints.append({
                "name": cp.name,
                "path": str(cp),
                "step": int(cp.name.split("-")[1]),
                "created": datetime.fromtimestamp(cp.stat().st_mtime).isoformat()
            })
    
    return sorted(checkpoints, key=lambda x: x["step"])


@router.post("/resume/{task_id}/{checkpoint_name}")
async def resume_training(task_id: str, checkpoint_name: str):
    """从检查点恢复训练"""
    state = get_state()
    settings = get_config()
    
    if await state.is_training():
        raise HTTPException(status_code=400, detail="Training already in progress")
    
    # 查找检查点
    output_dir = settings.outputs_dir_resolved / f"train_{task_id[:8]}"
    checkpoint_path = output_dir / "checkpoints" / checkpoint_name
    
    if not checkpoint_path.exists():
        raise HTTPException(status_code=404, detail="Checkpoint not found")
    
    # 加载原配�?    history = await state.get_history()
    original_record = None
    for r in history:
        if r.id == task_id:
            original_record = r
            break
    
    if not original_record:
        raise HTTPException(status_code=404, detail="Training record not found")
    
    # 创建新配�?    config_dict = original_record.config
    config_dict["resume_from_checkpoint"] = str(checkpoint_path)
    config = TrainingConfigInput(**config_dict)
    
    # 启动新训�?    return await start_training(config)


@router.post("/check-resources", response_model=ResourceCheckResponse)
async def check_resources(
    method: str = Query(default="qlora", description="微调方法"),
    model_size: str = Query(default="7B", description="模型大小估计"),
    required_vram: float = Query(default=6.0, description="预计需要显�?(GB)")
):
    """检查训练资�?
    在开始训练前检查系统资源，并提供智能降级建�?    """
    result = pre_training_resource_check(
        required_vram_gb=required_vram,
        method=method,
        model_size=model_size
    )
    
    return ResourceCheckResponse(**result)


class QueueTaskResponse(BaseModel):
    """队列任务响应"""
    task_id: str
    status: str
    priority: str
    queued_at: str
    message: str


class ValidationResult(BaseModel):
    """P1-2: 训练验证结果"""
    passed: bool = True
    errors: List[str] = []
    warnings: List[str] = []


class TrainingValidator:
    """P1-2: 训练验证�?""
    
    @staticmethod
    async def validate_config(config: TrainingConfigInput, settings: Settings) -> ValidationResult:
        """P1-2: 验证训练配置"""
        result = ValidationResult()
        
        # 1. 资源验证
        TrainingValidator._validate_resources(config, result)
        
        # 2. 数据集验�?        await TrainingValidator._validate_dataset(config, settings, result)
        
        # 3. 模型验证
        await TrainingValidator._validate_model(config, settings, result)
        
        # 4. 参数合理性验�?        TrainingValidator._validate_parameters(config, result)
        
        return result
    
    @staticmethod
    def _validate_resources(config: TrainingConfigInput, result: ValidationResult):
        """P1-2: 资源验证"""
        try:
            import torch
            
            if not torch.cuda.is_available():
                result.errors.append("CUDA 不可用，无法进行 GPU 训练")
                return
            
            # VRAM 估算
            estimated_vram = TrainingValidator._estimate_vram(
                config.model_id,
                config.method,
                config.batch_size,
                config.max_seq_length
            )
            
            available_vram = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
            allocated_vram = torch.cuda.memory_allocated(0) / (1024 ** 3)
            free_vram = available_vram - allocated_vram
            
            if free_vram < estimated_vram * 0.9:
                result.warnings.append(
                    f"预计需�?{estimated_vram:.1f}GB VRAM, 可用 {free_vram:.1f}GB"
                )
        except Exception as e:
            result.warnings.append(f"资源检查失败：{e}")
    
    @staticmethod
    def _estimate_vram(model_id: str, method: str, batch_size: int, max_seq_length: int) -> float:
        """估算 VRAM 需�?""
        # 基础模型大小估算
        if "13B" in model_id or "14B" in model_id:
            base_vram = 8.0
        elif "7B" in model_id or "8B" in model_id:
            base_vram = 4.0
        elif "3B" in model_id:
            base_vram = 2.0
        else:
            base_vram = 4.0  # 默认
        
        # QLoRA 减少显存
        if method == "qlora" or (hasattr(method, 'lower') and 'qlora' in method.lower()):
            base_vram *= 0.6
        
        # 批次大小影响
        if batch_size > 4:
            base_vram *= 1.2
        
        # 序列长度影响
        if max_seq_length > 1024:
            base_vram *= 1.3
        
        return base_vram
    
    @staticmethod
    async def _validate_dataset(config: TrainingConfigInput, settings: Settings, result: ValidationResult):
        """P1-2: 数据集验�?""
        try:
            dataset_path = settings.datasets_dir_resolved / config.dataset_id
            
            if not dataset_path.exists():
                result.errors.append(f"数据集不存在：{config.dataset_id}")
                return
            
            # 验证文件格式
            dataset_file = None
            for ext in [".json", ".jsonl"]:
                for f in dataset_path.glob(f"*{ext}"):
                    dataset_file = f
                    break
                if dataset_file:
                    break
            
            if not dataset_file:
                result.errors.append(f"不支持的数据集格式，需�?.json �?.jsonl")
                return
            
            # 验证数据内容
            import json
            with open(dataset_file, 'r', encoding='utf-8') as f:
                content = f.read()
                try:
                    data = json.loads(content)

                    # 检查必需字段
                    if isinstance(data, list) and len(data) > 0:
                        first_item = data[0]
                        if isinstance(first_item, dict):
                            if 'messages' not in first_item and 'text' not in first_item and 'content' not in first_item:
                                result.errors.append("数据集缺少必需字段：messages �?text")
                    elif isinstance(data, dict):
                        if 'messages' not in data and 'text' not in data and 'content' not in data:
                            result.errors.append("数据集缺少必需字段：messages �?text")
                except json.JSONDecodeError as e:
                    result.errors.append(f"JSON 格式错误：{e}")
        except Exception as e:
            result.errors.append(f"数据集验证失败：{e}")
    
    @staticmethod
    async def _validate_model(config: TrainingConfigInput, settings: Settings, result: ValidationResult):
        """P1-2: 模型验证"""
        try:
            model_path = settings.models_dir_resolved / config.model_id
            
            if not model_path.exists():
                result.errors.append(f"模型不存在：{config.model_id}")
                return
            
            # 验证模型配置
            config_file = model_path / "config.json"
            if config_file.exists():
                import json
                with open(config_file) as f:
                    model_config = json.load(f)
                
                # 检查模型类�?                model_type = model_config.get("model_type", "")
                supported_types = ["llama", "mistral", "gemma", "qwen", "chatglm", "baichuan"]
                if model_type and model_type not in supported_types:
                    result.warnings.append(
                        f"模型类型 '{model_type}' 可能不受支持，已知支持：{supported_types}"
                    )
        except Exception as e:
            result.warnings.append(f"模型验证失败：{e}")
    
    @staticmethod
    def _validate_parameters(config: TrainingConfigInput, result: ValidationResult):
        """P1-2: 参数合理性验�?""
        # 学习率范�?        if not (1e-6 <= config.learning_rate <= 1e-3):
            result.warnings.append(
                f"学习�?{config.learning_rate} 可能不合理，推荐范围�?e-6 ~ 1e-3"
            )
        
        # batch_size �?gradient_accumulation 组合
        effective_batch = config.batch_size * config.gradient_accumulation
        if effective_batch < 4:
            result.warnings.append(
                f"有效批次大小 {effective_batch} 过小，可能影响训练稳定�?
            )
        elif effective_batch > 128:
            result.warnings.append(
                f"有效批次大小 {effective_batch} 过大，可能导�?OOM"
            )
        
        # LoRA 参数
        if config.rank > 64:
            result.warnings.append(
                f"LoRA rank={config.rank} 较高，可能导致过拟合"
            )
        
        # epochs
        if config.epochs > 10:
            result.warnings.append(
                f"训练轮数 {config.epochs} 较多，注意过拟合风险"
            )


@router.post("/start", response_model=TrainingRecordResponse)
async def start_training(
    config: TrainingConfigInput,
    skip_resource_check: bool = False,
    use_queue: bool = False,
    priority: str = "normal"
):
    """开始训�?
    Args:
        config: 训练配置
        skip_resource_check: 是否跳过资源检�?        use_queue: 是否使用队列模式
        priority: 任务优先�?(urgent/high/normal/low)
    """
    state = get_state()
    settings = get_config()

    # 检查是否已有训练在进行
    if await state.is_training():
        raise HTTPException(status_code=400, detail="Training already in progress")

    # 验证模型和数据集
    model_path = settings.models_dir_resolved / config.model_id
    if not model_path.exists():
        raise HTTPException(status_code=404, detail=f"Model not found: {config.model_id}")

    dataset_path = settings.datasets_dir_resolved / config.dataset_id
    if not dataset_path.exists():
        raise HTTPException(status_code=404, detail=f"Dataset not found: {config.dataset_id}")

    # 查找数据集文�?    dataset_file = None
    for ext in [".json", ".jsonl"]:
        for pattern in [f"{config.dataset_id}{ext}", "data{ext}", f"*{ext}"]:
            potential_file = dataset_path / pattern
            if potential_file.exists():
                dataset_file = potential_file
                break
            for f in dataset_path.glob(pattern):
                dataset_file = f
                break
            if dataset_file:
                break
        if dataset_file:
            break

    if not dataset_file:
        raise HTTPException(status_code=404, detail=f"Dataset file not found in: {config.dataset_id}")

    # P2-4: 应用显存预设配置
    config = _apply_memory_preset(config)

    # P2-3: 应用精度预设配置
    config = _apply_precision_preset(config)

    # 资源预检（除非明确跳过）
    if not skip_resource_check:
        # P1-2: 增强验证
        validation_result = await TrainingValidator.validate_config(config, settings)
        
        # 记录验证结果
        for warning in validation_result.warnings:
            logger.warning(f"验证警告：{warning}")
        for error in validation_result.errors:
            logger.error(f"验证错误：{error}")
        
        # 如果有严重错误，阻止训练启动
        if validation_result.errors:
            raise HTTPException(
                status_code=400,
                detail=f"配置验证失败：{'�?.join(validation_result.errors)}"
            )
        
        # 原有资源检查作为补�?        model_size_gb = 4.0
        if "13B" in config.model_id or "14B" in config.model_id:
            model_size_gb = 8.0
        elif "3B" in config.model_id:
            model_size_gb = 2.0
        elif "1.5B" in config.model_id or "1B" in config.model_id:
            model_size_gb = 1.0

        if config.method == "qlora" and config.quantization == 4:
            model_size_gb *= 0.6

        resource_check = pre_training_resource_check(
            required_vram_gb=model_size_gb,
            method=config.method,
            model_size=config.model_id
        )

        for warning in resource_check.get("warnings", []):
            logger.warning(f"资源检查警告：{warning}")

        if not resource_check["passed"] and resource_check["recommended_config"]:
            recommended = resource_check["recommended_config"]
            logger.info(f"应用推荐配置：{recommended}")

            if "method" in recommended:
                config.method = recommended["method"]
            if "quantization" in recommended:
                config.quantization = recommended["quantization"]
            if "batch_size" in recommended:
                config.batch_size = recommended["batch_size"]
            if "max_seq_length" in recommended:
                config.max_seq_length = recommended["max_seq_length"]

    # 创建输出目录
    record_id = str(uuid.uuid4())
    output_path = settings.outputs_dir_resolved / f"train_{record_id[:8]}"
    output_path.mkdir(parents=True, exist_ok=True)

    # 创建训练记录
    record = TrainingRecord(
        id=record_id,
        model_name=config.model_id,
        dataset_name=config.dataset_id,
        method=config.method,
        status="queued" if use_queue else "running",
        start_time=datetime.now().isoformat(),
        config=config.model_dump(),
        output_path=str(output_path),
        checkpoint_path=None,
    )

    await state.set_current_record(record)
    config.output_path = str(output_path)

    # 定义训练启动函数
    def run_training():
        training_thread(config, str(model_path), str(dataset_file), state, record)

    if use_queue:
        # 使用队列模式
        priority_map = {
            "urgent": TaskPriority.URGENT,
            "high": TaskPriority.HIGH,
            "normal": TaskPriority.NORMAL,
            "low": TaskPriority.LOW,
        }
        task_priority = priority_map.get(priority.lower(), TaskPriority.NORMAL)
        
        queue = get_training_queue()
        success = queue.submit(
            task_id=record_id,
            config=config,
            callback=run_training,
            priority=task_priority
        )
        
        if not success:
            raise HTTPException(status_code=503, detail="Task queue is full")
        
        logger.info(f"训练任务已加入队列：{record_id}")
        return TrainingRecordResponse(**record.model_dump())
    else:
        # 直接启动模式
        thread = threading.Thread(
            target=run_training,
            daemon=True
        )
        await state.register_training_task(record_id, thread)
        thread.start()
        
        logger.info(f"训练任务已启动：{record_id}")
        return TrainingRecordResponse(**record.model_dump())


@router.get("/queue/status")
async def get_queue_status():
    """获取任务队列状�?""
    queue = get_training_queue()
    return queue.get_queue_status()


@router.get("/queue/task/{task_id}")
async def get_task_status(task_id: str):
    """获取任务状�?""
    queue = get_training_queue()
    status = queue.get_task_status(task_id)
    
    if status is None:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return status


@router.post("/queue/cancel/{task_id}")
async def cancel_task(task_id: str):
    """取消队列中的任务"""
    queue = get_training_queue()
    
    if queue.cancel(task_id):
        return {"message": f"Task {task_id} cancelled"}
    
    raise HTTPException(status_code=400, detail="Task not found or already running")
