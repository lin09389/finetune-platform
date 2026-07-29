"""
工具函数模块（重构版）
修复:
- P2-3: 使用设备信息缓存
- PERF-4: 优化 GPU 内存清理策略
"""
import gc
import hashlib
import threading
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

from core.logging import get_logger

logger = get_logger(__name__)

_device_info_cache: dict[str, Any] | None = None
_device_info_lock = threading.Lock()
_device_info_cache_time: float = 0
DEVICE_INFO_CACHE_TTL = 5.0

_vram_cache: dict[str, Any] = {"value": 0.0, "time": 0}
_vram_cache_lock = threading.Lock()
VRAM_CACHE_TTL = 0.5


def get_vram_usage(use_cache: bool = True) -> float:
    """获取 VRAM 使用量 (GB) - 带缓存"""
    try:
        current_time = time.time()

        if use_cache:
            with _vram_cache_lock:
                if current_time - _vram_cache["time"] < VRAM_CACHE_TTL:
                    return float(_vram_cache["value"])

        import torch

        if torch.cuda.is_available():
            value = torch.cuda.memory_allocated(0) / (1024 ** 3)

            if use_cache:
                with _vram_cache_lock:
                    _vram_cache["value"] = value
                    _vram_cache["time"] = current_time

            return float(value)
    except Exception as e:
        logger.debug(f"获取 VRAM 使用量失败：{e}")
    return 0.0


def get_available_memory() -> float | None:
    """获取可用 VRAM (GB)"""
    try:
        import torch

        if torch.cuda.is_available():
            total = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
            allocated = torch.cuda.memory_allocated(0) / (1024 ** 3)
            return float(total - allocated)
    except Exception as e:
        logger.debug(f"获取可用内存失败：{e}")
    return None


def pre_training_resource_check(
    required_vram_gb: float = 6.0,
    method: str = "qlora",
    model_size: str = "7B"
) -> dict[str, Any]:
    """
    训练前资源检查 + 智能降级建议

    Args:
        required_vram_gb: 预计需要的显存 (GB)
        method: 微调方法 (qlora/lora)
        model_size: 模型大小

    Returns:
        检查结果和建议
    """
    result: dict[str, Any] = {
        "passed": True,
        "available_vram": 0.0,
        "required_vram": required_vram_gb,
        "suggestions": [],
        "warnings": [],
        "recommended_config": {}
    }

    try:
        import torch

        if not torch.cuda.is_available():
            result["passed"] = False
            result["warnings"].append("CUDA 不可用，无法进行 GPU 训练")
            return result

        total_vram = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
        allocated_vram = torch.cuda.memory_allocated(0) / (1024 ** 3)
        available_vram = total_vram - allocated_vram

        result["available_vram"] = round(available_vram, 2)
        result["device_name"] = torch.cuda.get_device_properties(0).name

        if available_vram < required_vram_gb:
            result["passed"] = False

            if method == "lora":
                result["suggestions"].append("建议切换到 QLoRA 模式以减少显存占用")
                result["recommended_config"]["method"] = "qlora"

            if available_vram < 4.0:
                result["suggestions"].append("显存严重不足，建议使用更小的模型或更低的精度")
                result["recommended_config"]["quantization"] = 4
                result["recommended_config"]["batch_size"] = 1
            elif available_vram < 6.0:
                result["suggestions"].append("显存不足，建议降低 batch_size 和 sequence_length")
                result["recommended_config"]["batch_size"] = 1
                result["recommended_config"]["max_seq_length"] = 256
            else:
                result["suggestions"].append("建议降低 batch_size 和 sequence_length")
                result["recommended_config"]["batch_size"] = max(1, 2)

        elif available_vram < required_vram_gb * 1.2:
            result["warnings"].append("可用显存接近阈值，训练过程中可能遇到 OOM")
            result["suggestions"].append("建议关闭其他占用 GPU 的程序")

    except Exception as e:
        logger.error(f"资源检查失败：{e}")
        result["passed"] = False
        result["warnings"].append(f"资源检查出错：{str(e)}")

    return result


def calculate_file_hash(file_path: Path) -> str:
    """计算文件 SHA256 哈希"""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def validate_file_type(file_path: Path, allowed_types: list[str]) -> bool:
    """验证文件类型"""
    return file_path.suffix.lower() in allowed_types


def check_file_size(file_path: Path, max_size: int) -> bool:
    """检查文件大小"""
    return file_path.stat().st_size <= max_size


def safe_filename(filename: str) -> str:
    """生成安全的文件名"""
    unsafe_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|', '\0']
    for char in unsafe_chars:
        filename = filename.replace(char, '_')
    return filename.strip()


def format_bytes(size: float) -> str:
    """格式化字节大小为人类可读格式"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"


def format_time(seconds: float) -> str:
    """格式化时间为人类可读格式"""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    elif seconds < 86400:
        hours = seconds / 3600
        return f"{hours:.1f}h"
    else:
        days = seconds / 86400
        return f"{days:.1f}d"


class GPUMemoryCleaner:
    """
    GPU 内存清理器 - 智能清理策略

    PERF-4: 优化 GPU 内存清理
    """

    CLEANUP_COOLDOWN = 2.0
    AGGRESSIVE_CLEANUP_INTERVAL = 300.0

    _last_cleanup_time: float = 0
    _last_aggressive_cleanup: float = 0
    _lock = threading.Lock()

    @classmethod
    def cleanup(cls, aggressive: bool = False, force: bool = False) -> bool:
        """
        智能清理 GPU 内存

        Args:
            aggressive: 是否激进清理
            force: 是否强制清理（忽略冷却时间）

        Returns:
            是否清理成功
        """
        try:
            import torch

            if not torch.cuda.is_available():
                return False

            current_time = time.time()

            with cls._lock:
                if not force:
                    if current_time - cls._last_cleanup_time < cls.CLEANUP_COOLDOWN:
                        return True

                    if aggressive and current_time - cls._last_aggressive_cleanup < cls.AGGRESSIVE_CLEANUP_INTERVAL:
                        aggressive = False

                cls._last_cleanup_time = current_time

                torch.cuda.synchronize()
                torch.cuda.empty_cache()

                gc.collect()

                if aggressive:
                    cls._last_aggressive_cleanup = current_time
                    cls._do_aggressive_cleanup()

                vram_used = torch.cuda.memory_allocated(0) / (1024 ** 3)
                vram_total = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
                logger.debug(f"显存清理完成：{vram_used:.2f}/{vram_total:.2f}GB")

                return True

        except Exception as e:
            logger.warning(f"清理 GPU 内存失败：{e}")
        return False

    @classmethod
    def _do_aggressive_cleanup(cls):
        """执行激进清理"""
        try:
            import torch

            torch.cuda.reset_peak_memory_stats()

            for i in range(torch.cuda.device_count()):
                with torch.cuda.device(i):
                    mem_before = torch.cuda.memory_reserved()

                    torch.cuda.empty_cache()
                    torch.cuda.synchronize()

                    mem_after = torch.cuda.memory_reserved()

                    logger.debug(
                        f"GPU {i}: 释放 {(mem_before - mem_after) / (1024**3):.2f}GB"
                    )

        except Exception as e:
            logger.warning(f"激进清理失败：{e}")

    @classmethod
    def reset_counters(cls):
        """重置计数器（用于测试）"""
        cls._last_cleanup_time = 0
        cls._last_aggressive_cleanup = 0


def cleanup_gpu_memory(aggressive: bool = False):
    """
    清理 GPU 内存 - 智能清理版本

    PERF-4: 使用智能清理策略，减少不必要的清理操作

    Args:
        aggressive: 是否激进清理（清理所有 CUDA 缓存，适合长时运行后清理）

    Returns:
        bool: 是否清理成功
    """
    return GPUMemoryCleaner.cleanup(aggressive=aggressive)


def safe_cleanup_model(model: Any):
    """
    安全清理模型占用资源 - 增强版
    Args:
        model: 需要清理的模型对象
    """
    try:

        if model is None:
            return

        if hasattr(model, 'base_model'):
            try:
                if hasattr(model, 'merge_and_unload'):
                    pass
            except Exception:
                pass

        if hasattr(model, 'cpu'):
            with suppress(Exception):
                model.cpu()

        if hasattr(model, 'modules'):
            for _name, module in list(model.named_modules()):
                try:
                    if hasattr(module, 'weight'):
                        module.weight = None
                    if hasattr(module, 'bias'):
                        module.bias = None
                except Exception:
                    pass

        del model

        cleanup_gpu_memory()

        logger.debug("模型资源已清理")
    except Exception as e:
        logger.warning(f"清理模型资源失败：{e}")


def get_device_info(use_cache: bool = True) -> dict:
    """
    获取设备信息 - P2-3: 使用缓存

    Args:
        use_cache: 是否使用缓存
    """
    global _device_info_cache, _device_info_cache_time

    current_time = time.time()

    if use_cache:
        with _device_info_lock:
            if (_device_info_cache is not None and
                current_time - _device_info_cache_time < DEVICE_INFO_CACHE_TTL):
                return _device_info_cache.copy()

    try:
        import torch

        info = {
            "cuda_available": torch.cuda.is_available(),
            "device_count": torch.cuda.device_count() if torch.cuda.is_available() else 0,
            "device_name": "",
            "memory_total": 0.0,
            "memory_allocated": 0.0,
            "memory_reserved": 0.0,
        }

        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            info["device_name"] = props.name
            info["memory_total"] = props.total_memory / (1024 ** 3)
            info["memory_allocated"] = torch.cuda.memory_allocated(0) / (1024 ** 3)
            info["memory_reserved"] = torch.cuda.memory_reserved(0) / (1024 ** 3)

        if use_cache:
            with _device_info_lock:
                _device_info_cache = info
                _device_info_cache_time = current_time

        return info
    except Exception as e:
        logger.error(f"获取设备信息失败：{e}")
        return {
            "cuda_available": False,
            "device_count": 0,
            "device_name": "Unknown",
            "memory_total": 0.0,
            "memory_allocated": 0.0,
            "memory_reserved": 0.0,
        }


def clear_device_info_cache():
    """清除设备信息缓存"""
    global _device_info_cache, _device_info_cache_time
    with _device_info_lock:
        _device_info_cache = None
        _device_info_cache_time = 0
