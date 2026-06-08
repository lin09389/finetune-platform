"""本地推理运行时策略。"""
from __future__ import annotations

from typing import Any

from core.config import get_settings
from core.hardware_profile import build_hardware_profile
from core.quantization import QuantizationConfig, QuantizationDetector, QuantizationType
from core.utils import get_device_info


def _pick_quantization(
    backend: str,
    profile: dict[str, Any],
    detected_quant: QuantizationType,
) -> QuantizationType:
    if detected_quant in {QuantizationType.GGUF, QuantizationType.GGML, QuantizationType.GPTQ, QuantizationType.AWQ}:
        return detected_quant

    recommended = profile.get("recommended_quantization", "int8")
    if backend == "llama-cpp":
        return QuantizationType.GGUF if detected_quant == QuantizationType.NONE else detected_quant

    if recommended == "int4":
        return QuantizationType.INT4
    if recommended == "int8":
        return QuantizationType.INT8
    return QuantizationType.NONE


def build_runtime_policy(
    *,
    model_path: str,
    backend: str,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """根据设备画像、模型类型和请求参数生成运行策略。"""
    options = options or {}
    settings = get_settings()
    device_info = get_device_info(use_cache=False)
    hardware_profile = build_hardware_profile(device_info)
    detected_quant = QuantizationDetector.detect_quant_type(model_path)
    quant_type = _pick_quantization(backend, hardware_profile, detected_quant)
    quant_config = QuantizationConfig(quant_type=quant_type)

    recommended_threads = hardware_profile["recommended_threads"]
    recommended_batch = max(1, min(options.get("num_batch", hardware_profile["recommended_batch_size"]), settings.max_batch_size))
    num_ctx = options.get("num_ctx", hardware_profile["recommended_max_context"])

    policy = {
        "backend": backend,
        "hardware_profile": hardware_profile,
        "quantization": quant_config.to_dict(),
        "model_path": model_path,
        "num_ctx": num_ctx,
        "num_batch": recommended_batch,
        "num_thread": options.get("num_thread", recommended_threads),
        "batch_size": recommended_batch,
        "enable_batching": bool(settings.enable_batching and backend != "cloud"),
        "max_batch_size": max(1, min(recommended_batch, settings.max_batch_size)),
        "max_batch_wait_ms": settings.max_batch_wait_ms,
        "warmup_prompt": options.get("warmup_prompt", "请用一句话介绍你自己。"),
        "warmup_enabled": backend != "cloud",
        "lora_adapter": options.get("lora_adapter"),
        "torch_dtype": "float16" if hardware_profile["accelerator"] == "gpu" else "float32",
        "device_map": "auto",
        "load_in_8bit": quant_type == QuantizationType.INT8,
        "load_in_4bit": quant_type == QuantizationType.INT4,
        "enable_flash_attention": bool(settings.enable_flash_attention),
        "kv_cache_dtype": settings.kv_cache_dtype,
        "enable_prefix_caching": bool(settings.enable_prefix_caching),
    }

    if backend == "llama-cpp":
        gpu_memory = hardware_profile.get("gpu_memory_total_gb", 0.0)
        if hardware_profile["accelerator"] == "gpu":
            if gpu_memory <= 4.5:
                policy["n_gpu_layers"] = 28
            elif gpu_memory <= 8.5:
                policy["n_gpu_layers"] = -1
            else:
                policy["n_gpu_layers"] = -1
        else:
            policy["n_gpu_layers"] = 0

    return policy
