"""
Flash Attention 2 检测模�?
提供 Flash Attention 2 的可用性检测和自动降级功能
"""
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# 缓存检测结果，避免重复检�?_flash_attn_available: Optional[bool] = None
_flash_attn_version: Optional[str] = None
_gpu_architecture_supported: Optional[bool] = None


def get_gpu_compute_capability() -> Optional[Tuple[int, int]]:
    """
    获取 GPU 计算能力版本
    
    Returns:
        Tuple[int, int]: (major, minor) 计算能力版本，如 (8, 6) 表示 SM 86
        None: 如果 CUDA 不可�?    """
    try:
        import torch
        
        if not torch.cuda.is_available():
            return None
        
        device = torch.cuda.current_device()
        capability = torch.cuda.get_device_capability(device)
        return capability
        
    except Exception as e:
        logger.debug(f"获取 GPU 计算能力失败：{e}")
        return None


def is_gpu_architecture_supported() -> bool:
    """
    检�?GPU 架构是否支持 Flash Attention 2
    
    Flash Attention 2 需�?Ampere 架构及以上：
    - RTX 30 系列 (Ampere, SM 80+)
    - RTX 40 系列 (Ada Lovelace, SM 89+)
    - A100, A10, A30, A40 �?(Ampere)
    - H100, H200 �?(Hopper, SM 90+)
    
    Returns:
        bool: 是否支持 Flash Attention 2
    """
    global _gpu_architecture_supported
    
    if _gpu_architecture_supported is not None:
        return _gpu_architecture_supported
    
    try:
        capability = get_gpu_compute_capability()
        
        if capability is None:
            logger.debug("CUDA 不可用，GPU 架构不支�?Flash Attention 2")
            _gpu_architecture_supported = False
            return False
        
        major, minor = capability
        
        # Ampere 架构及以�?(SM 8.0+)
        # 包括：RTX 30 系列 (SM 86), RTX 40 系列 (SM 89), A100 (SM 80), H100 (SM 90)
        is_supported = major >= 8
        
        if is_supported:
            logger.info(f"GPU 架构支持 Flash Attention 2：SM {major}.{minor}")
        else:
            logger.info(f"GPU 架构不支�?Flash Attention 2：SM {major}.{minor}（需�?SM 8.0+�?)
        
        _gpu_architecture_supported = is_supported
        return is_supported
        
    except Exception as e:
        logger.warning(f"检�?GPU 架构时出错：{e}")
        _gpu_architecture_supported = False
        return False


def is_flash_attn_2_installed() -> Tuple[bool, Optional[str]]:
    """
    检�?flash-attn 库是否已安装
    
    Returns:
        Tuple[bool, Optional[str]]: (是否安装, 版本�?
    """
    global _flash_attn_version
    
    if _flash_attn_version is not None:
        return _flash_attn_version is not None, _flash_attn_version
    
    try:
        import flash_attn
        version = getattr(flash_attn, '__version__', 'unknown')
        _flash_attn_version = version
        logger.info(f"flash-attn 库已安装：版�?{version}")
        return True, version
        
    except ImportError:
        logger.debug("flash-attn 库未安装")
        _flash_attn_version = None
        return False, None
        
    except Exception as e:
        logger.warning(f"检�?flash-attn 库时出错：{e}")
        _flash_attn_version = None
        return False, None


def is_flash_attn_2_available() -> bool:
    """
    检�?Flash Attention 2 是否可用
    
    需要同时满足以下条件：
    1. GPU 架构支持（Ampere 及以上）
    2. flash-attn 库已安装
    3. CUDA 可用
    
    Returns:
        bool: Flash Attention 2 是否可用
    """
    global _flash_attn_available
    
    if _flash_attn_available is not None:
        return _flash_attn_available
    
    # 检�?GPU 架构
    if not is_gpu_architecture_supported():
        logger.info("Flash Attention 2 不可用：GPU 架构不支�?)
        _flash_attn_available = False
        return False
    
    # 检�?flash-attn �?    installed, version = is_flash_attn_2_installed()
    if not installed:
        logger.info("Flash Attention 2 不可用：flash-attn 库未安装")
        _flash_attn_available = False
        return False
    
    # 检�?CUDA 是否可用
    try:
        import torch
        if not torch.cuda.is_available():
            logger.info("Flash Attention 2 不可用：CUDA 不可�?)
            _flash_attn_available = False
            return False
    except ImportError:
        logger.info("Flash Attention 2 不可用：PyTorch 未安�?)
        _flash_attn_available = False
        return False
    
    logger.info(f"Flash Attention 2 可用：版�?{version}")
    _flash_attn_available = True
    return True


def get_attention_implementation(force_eager: bool = False) -> str:
    """
    获取推荐�?attention 实现方式
    
    Args:
        force_eager: 是否强制使用 eager 实现
    
    Returns:
        str: "flash_attention_2" �?"eager"
    """
    if force_eager:
        logger.info("使用 eager attention（强制）")
        return "eager"
    
    if is_flash_attn_2_available():
        logger.info("使用 Flash Attention 2")
        return "flash_attention_2"
    
    logger.info("使用 eager attention（降级）")
    return "eager"


def get_flash_attention_info() -> dict:
    """
    获取 Flash Attention 详细信息
    
    Returns:
        dict: 包含检测结果的详细信息
    """
    capability = get_gpu_compute_capability()
    installed, version = is_flash_attn_2_installed()
    
    info = {
        "available": is_flash_attn_2_available(),
        "gpu_architecture_supported": is_gpu_architecture_supported(),
        "flash_attn_installed": installed,
        "flash_attn_version": version,
        "gpu_compute_capability": f"SM {capability[0]}.{capability[1]}" if capability else None,
        "recommended_implementation": get_attention_implementation(),
    }
    
    return info


def reset_detection_cache():
    """
    重置检测缓�?    
    用于�?GPU 状态变化后重新检�?    """
    global _flash_attn_available, _flash_attn_version, _gpu_architecture_supported
    
    _flash_attn_available = None
    _flash_attn_version = None
    _gpu_architecture_supported = None
    
    logger.debug("Flash Attention 检测缓存已重置")
