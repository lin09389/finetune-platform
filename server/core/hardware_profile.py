"""本地推理硬件画像与推荐策略。"""
from __future__ import annotations

from typing import Any

import psutil

from core.utils import get_device_info as get_core_device_info


def build_hardware_profile(device_info: dict[str, Any] | None = None) -> dict[str, Any]:
    """根据当前机器规格给出本地推理推荐策略。"""
    info = device_info or get_core_device_info(use_cache=False)
    system_memory_total = round(psutil.virtual_memory().total / (1024 ** 3), 2)

    cuda_available = bool(info.get("cuda_available"))
    vram_total = float(info.get("memory_total", 0.0) or 0.0)
    cpu_count = psutil.cpu_count() or 4

    accelerator = "cpu"
    if cuda_available:
        accelerator = "gpu"
    elif info.get("mps_available"):
        accelerator = "mps"
    elif info.get("npu_available"):
        accelerator = "npu"

    profile = "cpu-only"
    recommended_backend = "huggingface"
    recommended_quantization = "int8"
    recommended_batch_size = 1
    recommended_threads = max(2, min(cpu_count, 8))
    max_context = 2048

    if accelerator == "gpu":
        if vram_total <= 4.5:
            profile = "gpu-4gb"
            recommended_backend = "llama-cpp"
            recommended_quantization = "int4"
            recommended_batch_size = 1
            recommended_threads = max(2, min(cpu_count, 6))
            max_context = 2048
        elif vram_total <= 8.5:
            profile = "gpu-8gb"
            recommended_backend = "llama-cpp"
            recommended_quantization = "int4"
            recommended_batch_size = 2
            recommended_threads = max(2, min(cpu_count, 8))
            max_context = 4096
        elif vram_total <= 16.5:
            profile = "gpu-16gb"
            recommended_backend = "huggingface"
            recommended_quantization = "int8"
            recommended_batch_size = 4
            recommended_threads = max(4, min(cpu_count, 12))
            max_context = 4096
        else:
            profile = "gpu-24gb-plus"
            recommended_backend = "huggingface"
            recommended_quantization = "fp16"
            recommended_batch_size = 8
            recommended_threads = max(4, min(cpu_count, 16))
            max_context = 8192
    elif accelerator == "npu":
        profile = "npu"
        recommended_backend = "huggingface"
        recommended_quantization = "int8"
        recommended_batch_size = 2
        max_context = 4096
    else:
        if system_memory_total <= 8:
            profile = "cpu-low-memory"
            recommended_backend = "llama-cpp"
            recommended_quantization = "int4"
            recommended_batch_size = 1
            recommended_threads = max(2, min(cpu_count, 4))
            max_context = 2048
        elif system_memory_total <= 16:
            profile = "cpu-mid-memory"
            recommended_backend = "llama-cpp"
            recommended_quantization = "int4"
            recommended_batch_size = 1
            recommended_threads = max(2, min(cpu_count, 8))
            max_context = 4096
        else:
            profile = "cpu-high-memory"
            recommended_backend = "huggingface"
            recommended_quantization = "int8"
            recommended_batch_size = 2
            recommended_threads = max(4, min(cpu_count, 12))
            max_context = 4096

    return {
        "profile": profile,
        "accelerator": accelerator,
        "recommended_backend": recommended_backend,
        "recommended_quantization": recommended_quantization,
        "recommended_batch_size": recommended_batch_size,
        "recommended_threads": recommended_threads,
        "recommended_max_context": max_context,
        "system_memory_total_gb": system_memory_total,
        "gpu_memory_total_gb": round(vram_total, 2),
        "cpu_count": cpu_count,
        "notes": [
            "优先为本地推理选择推荐后端和量化等级。",
            "低显存设备优先使用 GGUF/INT4，并保持较小 batch size。",
        ],
    }
