"""
设备管理 API
"""
import platform
from typing import Any

import psutil
from fastapi import APIRouter, HTTPException

from core.hardware_profile import build_hardware_profile
from core.logging import get_logger
from core.utils import get_device_info as get_core_device_info

logger = get_logger(__name__)

router = APIRouter()


def get_device_info() -> dict[str, Any]:
    """获取设备详细信息"""
    core_info = get_core_device_info(use_cache=False)
    info = {
        "platform": "unknown",
        "device_name": "Unknown",
        "vram_total": 0,
        "vram_used": 0,
        "vram_free": 0,
        "memory_total": 0,
        "memory_used": 0,
        "memory_free": 0,
        "cuda_available": False,
        "mps_available": False,
        "cpu_count": psutil.cpu_count(),
        "cpu_percent": psutil.cpu_percent(interval=1),
    }

    system = platform.system()

    if system == "Darwin":
        info["platform"] = "mac"
        info["device_name"] = f"Apple Silicon ({platform.processor()})"
        try:
            import torch
            info["mps_available"] = torch.backends.mps.is_available() if hasattr(torch, "backends") else False
        except ImportError:
            pass
        info["cuda_available"] = False
    elif system in ["Windows", "Linux"]:
        try:
            import torch

            if torch.cuda.is_available():
                info["platform"] = "cuda"
                info["cuda_available"] = True
                info["device_name"] = torch.cuda.get_device_name(0)
                info["vram_total"] = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
                info["vram_used"] = torch.cuda.memory_allocated(0) / (1024 ** 3)
                info["vram_free"] = info["vram_total"] - info["vram_used"]
            else:
                info["platform"] = "cpu"
                info["device_name"] = "CPU"
        except Exception as e:
            logger.warning(f"获取 CUDA 信息失败：{e}")
            info["platform"] = "cpu"

    # 系统内存
    mem = psutil.virtual_memory()
    info["memory_total"] = mem.total / (1024 ** 3)
    info["memory_used"] = mem.used / (1024 ** 3)
    info["memory_free"] = mem.available / (1024 ** 3)

    info["memory"] = {
        "total_gb": round(info["memory_total"], 2),
        "used_gb": round(info["memory_used"], 2),
        "free_gb": round(info["memory_free"], 2),
    }
    info["inference"] = {
        "memory_total_gb": round(core_info.get("memory_total", 0.0), 2),
        "memory_allocated_gb": round(core_info.get("memory_allocated", 0.0), 2),
        "memory_reserved_gb": round(core_info.get("memory_reserved", 0.0), 2),
    }
    info["hardware_profile"] = build_hardware_profile(
        {
            **core_info,
            "mps_available": info["mps_available"],
        }
    )

    return info


@router.get("/info")
async def get_device_info_endpoint():
    """获取设备信息"""
    try:
        return get_device_info()
    except Exception as e:
        logger.error(f"获取设备信息失败：{e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vram")
async def get_vram_info():
    """获取 VRAM 信息"""
    try:
        import torch

        if not torch.cuda.is_available():
            return {"error": "CUDA not available", "cuda_available": False}

        return {
            "cuda_available": True,
            "device_name": torch.cuda.get_device_name(0),
            "total_gb": round(torch.cuda.get_device_properties(0).total_memory / (1024 ** 3), 2),
            "allocated_gb": round(torch.cuda.memory_allocated(0) / (1024 ** 3), 2),
            "reserved_gb": round(torch.cuda.memory_reserved(0) / (1024 ** 3), 2),
            "free_gb": round(
                (torch.cuda.get_device_properties(0).total_memory - torch.cuda.memory_allocated(0)) / (1024 ** 3),
                2
            ),
        }
    except Exception as e:
        logger.error(f"获取 VRAM 信息失败：{e}")
        return {"error": str(e), "cuda_available": False}


@router.get("/memory")
async def get_memory_info():
    """获取系统内存信息"""
    try:
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()

        return {
            "virtual": {
                "total_gb": round(mem.total / (1024 ** 3), 2),
                "used_gb": round(mem.used / (1024 ** 3), 2),
                "available_gb": round(mem.available / (1024 ** 3), 2),
                "percent": mem.percent,
            },
            "swap": {
                "total_gb": round(swap.total / (1024 ** 3), 2),
                "used_gb": round(swap.used / (1024 ** 3), 2),
                "free_gb": round(swap.free / (1024 ** 3), 2),
                "percent": swap.percent,
            }
        }
    except Exception as e:
        logger.error(f"获取内存信息失败：{e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/disk")
async def get_disk_info():
    """获取磁盘信息"""
    try:
        partitions = psutil.disk_partitions()
        disk_info = []

        for partition in partitions:
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                disk_info.append({
                    "device": partition.device,
                    "mountpoint": partition.mountpoint,
                    "fstype": partition.fstype,
                    "total_gb": round(usage.total / (1024 ** 3), 2),
                    "used_gb": round(usage.used / (1024 ** 3), 2),
                    "free_gb": round(usage.free / (1024 ** 3), 2),
                    "percent": usage.percent,
                })
            except PermissionError:
                continue

        return {"partitions": disk_info}
    except Exception as e:
        logger.error(f"获取磁盘信息失败：{e}")
        raise HTTPException(status_code=500, detail=str(e))
