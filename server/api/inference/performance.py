"""
推理性能指标 API

提供性能监控和优化建�?"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import asyncio

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/inference", tags=["inference"])


class EngineConfig(BaseModel):
    """引擎配置"""
    engine: str = "huggingface"
    quantization: str = "none"
    batch_size: int = 1
    max_tokens: int = 2048
    temperature: float = 0.7
    use_cache: bool = True
    flash_attention: bool = False


class OptimizationSuggestion(BaseModel):
    """优化建议"""
    type: str
    title: str
    description: str
    impact: str
    suggested_value: Optional[Any] = None


class PerformanceMetrics(BaseModel):
    """性能指标"""
    tokens_per_second: float = 0.0
    first_token_latency: float = 0.0
    memory_usage: float = 0.0
    gpu_utilization: float = 0.0
    cache_hit_rate: float = 0.0
    batch_size: int = 1
    queue_length: int = 0


_metrics = PerformanceMetrics()
_request_times: List[float] = []
_token_counts: List[int] = []


def update_metrics(tokens: int, latency: float, memory: float):
    """更新性能指标"""
    global _metrics, _request_times, _token_counts
    
    now = datetime.now().timestamp()
    _request_times.append(now)
    _token_counts.append(tokens)
    
    _request_times = [t for t in _request_times if now - t < 60]
    _token_counts = _token_counts[-100:]
    
    if _request_times and _token_counts:
        total_tokens = sum(_token_counts)
        time_span = max(_request_times) - min(_request_times) if len(_request_times) > 1 else 1
        _metrics.tokens_per_second = total_tokens / max(time_span, 1)
    
    _metrics.first_token_latency = latency
    _metrics.memory_usage = memory


@router.get("/metrics", response_model=PerformanceMetrics)
async def get_metrics():
    """获取性能指标"""
    try:
        from core.config import get_settings
        settings = get_settings()
        
        try:
            import torch
            if torch.cuda.is_available():
                _metrics.gpu_utilization = torch.cuda.utilization()
                _metrics.memory_usage = torch.cuda.memory_allocated() / torch.cuda.max_memory_allocated() * 100
        except ImportError:
            pass
        
        try:
            from core.batching import get_batch_scheduler
            batch_scheduler = get_batch_scheduler()
            stats = batch_scheduler.get_all_stats()
            if stats:
                first_stats = list(stats.values())[0]
                _metrics.queue_length = first_stats.get("queue_size", 0)
                _metrics.batch_size = int(first_stats.get("avg_batch_size", 1))
        except ImportError:
            pass
        
        try:
            from core.kv_cache import get_cache_manager
            cache_manager = get_cache_manager()
            cache_stats = cache_manager.get_stats()
            _metrics.cache_hit_rate = cache_stats.hit_rate
        except ImportError:
            pass
        
    except Exception as e:
        logger.error(f"获取指标失败: {e}")
    
    return _metrics


@router.post("/suggestions")
async def get_suggestions(config: EngineConfig) -> Dict[str, List[OptimizationSuggestion]]:
    """获取优化建议"""
    suggestions = []
    
    if config.engine == "huggingface" and config.quantization == "none":
        suggestions.append(OptimizationSuggestion(
            type="performance",
            title="切换�?vLLM 引擎",
            description="vLLM 提供更高的推理吞吐量，支�?PagedAttention 和前缀缓存优化",
            impact="high",
            suggested_value="vllm",
        ))
    
    if config.quantization == "none" and _metrics.memory_usage > 70:
        suggestions.append(OptimizationSuggestion(
            type="memory",
            title="启用模型量化",
            description="当前显存占用较高，建议启�?INT4 �?GPTQ 量化以减少显存占�?30%+",
            impact="high",
            suggested_value="int4",
        ))
    
    if config.batch_size == 1 and _metrics.queue_length > 0:
        suggestions.append(OptimizationSuggestion(
            type="performance",
            title="增加批处理大�?,
            description="当前有排队请求，增加批处理大小可提升吞吐�?,
            impact="medium",
            suggested_value=4,
        ))
    
    if not config.flash_attention and config.engine == "vllm":
        suggestions.append(OptimizationSuggestion(
            type="performance",
            title="启用 Flash Attention",
            description="Flash Attention 2 可显著提升长序列推理速度",
            impact="medium",
            suggested_value=True,
        ))
    
    if not config.use_cache:
        suggestions.append(OptimizationSuggestion(
            type="performance",
            title="启用 KV Cache",
            description="KV Cache 可避免重复计算，显著提升推理速度",
            impact="medium",
            suggested_value=True,
        ))
    
    if _metrics.first_token_latency > 500:
        suggestions.append(OptimizationSuggestion(
            type="performance",
            title="首字延迟较高",
            description="首字延迟超过 500ms，建议检查模型加载或考虑使用更小的模�?,
            impact="high",
        ))
    
    if _metrics.cache_hit_rate < 0.3:
        suggestions.append(OptimizationSuggestion(
            type="performance",
            title="缓存命中率较�?,
            description="KV Cache 命中率较低，建议检查是否有重复的上下文或启用前缀缓存",
            impact="low",
        ))
    
    return {"suggestions": suggestions}


@router.post("/config")
async def update_config(config: EngineConfig) -> Dict[str, Any]:
    """更新推理配置"""
    try:
        from core.config import get_settings
        settings = get_settings()
        
        settings.inference_backend = config.engine
        
        logger.info(f"更新推理配置: {config.model_dump()}")
        
        return {
            "success": True,
            "message": "配置已更�?,
            "config": config.model_dump(),
        }
    
    except Exception as e:
        logger.error(f"更新配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/engines")
async def list_engines() -> Dict[str, Any]:
    """列出可用引擎"""
    engines = [
        {
            "id": "huggingface",
            "name": "HuggingFace Transformers",
            "description": "默认推理引擎，兼容性最�?,
            "features": ["流式输出", "LoRA 支持", "量化支持"],
            "recommended": False,
        },
        {
            "id": "vllm",
            "name": "vLLM",
            "description": "高性能推理引擎，支�?PagedAttention",
            "features": ["PagedAttention", "前缀缓存", "�?LoRA", "高吞吐量"],
            "recommended": True,
        },
        {
            "id": "ollama",
            "name": "Ollama",
            "description": "本地推理服务，支�?GGUF 模型",
            "features": ["GGUF 支持", "本地部署", "简单配�?],
            "recommended": False,
        },
    ]
    
    available = []
    for engine in engines:
        try:
            if engine["id"] == "vllm":
                import vllm
                available.append(engine)
            elif engine["id"] == "ollama":
                import ollama
                available.append(engine)
            else:
                available.append(engine)
        except ImportError:
            engine["available"] = False
            available.append(engine)
    
    return {"engines": available}


@router.get("/quantization")
async def list_quantization() -> Dict[str, Any]:
    """列出可用的量化方�?""
    quant_types = [
        {
            "id": "none",
            "name": "无量�?(FP16)",
            "description": "原始精度，最高质�?,
            "memory_reduction": "0%",
            "speed_impact": "基准",
        },
        {
            "id": "int8",
            "name": "INT8 量化",
            "description": "8位整数量�?,
            "memory_reduction": "~50%",
            "speed_impact": "轻微提升",
        },
        {
            "id": "int4",
            "name": "INT4 量化",
            "description": "4位整数量�?,
            "memory_reduction": "~75%",
            "speed_impact": "显著提升",
        },
        {
            "id": "gptq",
            "name": "GPTQ",
            "description": "训练后量化，保持较高精度",
            "memory_reduction": "~70%",
            "speed_impact": "显著提升",
        },
        {
            "id": "awq",
            "name": "AWQ",
            "description": "激活感知量�?,
            "memory_reduction": "~70%",
            "speed_impact": "显著提升",
        },
        {
            "id": "gguf",
            "name": "GGUF",
            "description": "llama.cpp 格式，支持多种量化级�?,
            "memory_reduction": "可变",
            "speed_impact": "取决于量化级�?,
        },
    ]
    
    return {"quantization_types": quant_types}
