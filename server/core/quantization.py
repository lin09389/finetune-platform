"""
量化模型支持模块

支持多种量化格式：
- GPTQ
- AWQ
- GGUF (llama-cpp-python)
"""
import os
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path
from enum import Enum
import json

logger = logging.getLogger(__name__)


class QuantizationType(str, Enum):
    """量化类型"""
    NONE = "none"
    GPTQ = "gptq"
    AWQ = "awq"
    GGUF = "gguf"
    GGML = "ggml"
    FP8 = "fp8"
    INT8 = "int8"
    INT4 = "int4"


class QuantizationConfig:
    """量化配置"""
    
    def __init__(
        self,
        quant_type: QuantizationType = QuantizationType.NONE,
        bits: int = 4,
        group_size: int = 128,
        desc_act: bool = True,
        use_exllama: bool = True,
    ):
        self.quant_type = quant_type
        self.bits = bits
        self.group_size = group_size
        self.desc_act = desc_act
        self.use_exllama = use_exllama
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "quant_type": self.quant_type.value,
            "bits": self.bits,
            "group_size": self.group_size,
            "desc_act": self.desc_act,
            "use_exllama": self.use_exllama,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QuantizationConfig":
        return cls(
            quant_type=QuantizationType(data.get("quant_type", "none")),
            bits=data.get("bits", 4),
            group_size=data.get("group_size", 128),
            desc_act=data.get("desc_act", True),
            use_exllama=data.get("use_exllama", True),
        )


class QuantizedModelInfo:
    """量化模型信息"""
    
    def __init__(
        self,
        model_path: str,
        quant_type: QuantizationType,
        original_size: Optional[int] = None,
        quantized_size: Optional[int] = None,
        bits: int = 4,
        model_type: str = "llama",
    ):
        self.model_path = model_path
        self.quant_type = quant_type
        self.original_size = original_size
        self.quantized_size = quantized_size
        self.bits = bits
        self.model_type = model_type
        
        if original_size and quantized_size:
            self.compression_ratio = (original_size - quantized_size) / original_size
        else:
            self.compression_ratio = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_path": self.model_path,
            "quant_type": self.quant_type.value,
            "original_size": self.original_size,
            "quantized_size": self.quantized_size,
            "bits": self.bits,
            "model_type": self.model_type,
            "compression_ratio": self.compression_ratio,
        }


class QuantizationDetector:
    """量化模型检测器"""
    
    QUANT_PATTERNS = {
        QuantizationType.GPTQ: [".gptq", "-GPTQ", "_GPTQ"],
        QuantizationType.AWQ: [".awq", "-AWQ", "_AWQ", ".quant"],
        QuantizationType.GGUF: [".gguf", ".ggml", "-q4", "-q8", "-q5", "-q2"],
        QuantizationType.GGML: [".ggml", "-ggml"],
    }
    
    @classmethod
    def detect_quant_type(cls, model_path: str) -> QuantizationType:
        """检测模型量化类型"""
        model_lower = model_path.lower()
        
        for quant_type, patterns in cls.QUANT_PATTERNS.items():
            for pattern in patterns:
                if pattern.lower() in model_lower:
                    logger.info(f"检测到量化类型: {quant_type.value} (匹配: {pattern})")
                    return quant_type
        
        logger.info("未检测到量化类型，使用 FP16")
        return QuantizationType.NONE
    
    @classmethod
    def get_model_info(cls, model_path: str) -> QuantizedModelInfo:
        """获取模型信息"""
        path = Path(model_path)
        
        if not path.exists():
            raise FileNotFoundError(f"模型文件不存在: {model_path}")
        
        if path.is_file():
            size = path.stat().st_size
            parent = path.parent
        else:
            total_size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
            size = total_size
            parent = path
        
        quant_type = cls.detect_quant_type(model_path)
        
        if quant_type == QuantizationType.NONE:
            return QuantizedModelInfo(
                model_path=model_path,
                quant_type=quant_type,
                original_size=size,
                quantized_size=None,
            )
        
        bits = cls._detect_bits(model_path)
        
        model_type = cls._detect_model_type(parent)
        
        return QuantizedModelInfo(
            model_path=model_path,
            quant_type=quant_type,
            quantized_size=size,
            bits=bits,
            model_type=model_type,
        )
    
    @classmethod
    def _detect_bits(cls, model_path: str) -> int:
        """检测量化位数"""
        model_lower = model_path.lower()
        
        if "q4" in model_lower or "_4" in model_lower:
            return 4
        elif "q5" in model_lower or "_5" in model_lower:
            return 5
        elif "q8" in model_lower or "_8" in model_lower:
            return 8
        elif "q2" in model_lower or "_2" in model_lower:
            return 2
        elif "q3" in model_lower or "_3" in model_lower:
            return 3
        
        return 4
    
    @classmethod
    def _detect_model_type(cls, model_dir: Path) -> str:
        """检测模型类型"""
        config_files = ["config.json", "config.yaml", "model_config.json"]
        
        for config_file in config_files:
            config_path = model_dir / config_file
            if config_path.exists():
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        config = json.load(f)
                    
                    if "model_type" in config:
                        return config["model_type"]
                    
                    if "architectures" in config:
                        return config["architectures"][0].lower()
                except Exception:
                    pass
        
        model_lower = model_dir.name.lower()
        if "llama" in model_lower:
            return "llama"
        elif "qwen" in model_lower:
            return "qwen"
        elif "baichuan" in model_lower:
            return "baichuan"
        elif "chatglm" in model_lower:
            return "chatglm"
        
        return "llama"


class QuantizationLoader:
    """量化模型加载器"""
    
    @staticmethod
    def get_loader_args(
        model_path: str,
        quant_config: QuantizationConfig,
    ) -> Dict[str, Any]:
        """获取模型加载参数"""
        
        if quant_config.quant_type == QuantizationType.GPTQ:
            return {
                "quantization_config": {
                    "bits": quant_config.bits,
                    "group_size": quant_config.group_size,
                    "desc_act": quant_config.desc_act,
                    "use_exllama": quant_config.use_exllama,
                }
            }
        
        elif quant_config.quant_type == QuantizationType.AWQ:
            return {
                "quantization_config": {
                    "bits": quant_config.bits,
                    "group_size": quant_config.group_size,
                },
                "use_awq": True,
            }
        
        elif quant_config.quant_type == QuantizationType.GGUF:
            return {
                "use_gguf": True,
                "gguf_path": model_path,
            }
        
        elif quant_config.quant_type in [QuantizationType.INT8, QuantizationType.INT4]:
            load_in_8bit = quant_config.quant_type == QuantizationType.INT8
            load_in_4bit = quant_config.quant_type == QuantizationType.INT4
            
            return {
                "load_in_8bit": load_in_8bit,
                "load_in_4bit": load_in_4bit,
            }
        
        return {}
    
    @staticmethod
    def estimate_vram_usage(
        model_path: str,
        quant_config: QuantizationConfig,
    ) -> int:
        """估算显存使用量（字节）"""
        import math
        
        model_info = QuantizationDetector.get_model_info(model_path)
        
        base_vram = 4 * 1024 * 1024 * 1024
        
        if model_info.quantized_size:
            if model_info.quant_type == QuantizationType.GPTQ:
                base_vram = model_info.quantized_size * 1.2
            elif model_info.quant_type == QuantizationType.AWQ:
                base_vram = model_info.quantized_size * 1.3
            elif model_info.quant_type == QuantizationType.GGUF:
                base_vram = model_info.quantized_size * 1.5
            else:
                base_vram = model_info.quantized_size * 1.2
        else:
            bits_to_bytes = {
                4: 0.5,
                8: 1.0,
                16: 2.0,
            }
            multiplier = bits_to_bytes.get(model_info.bits, 1.0)
            base_vram = 4 * 1024 * 1024 * 1024 * multiplier
        
        return int(base_vram)


def create_quantized_model(
    model_path: str,
    quant_type: Optional[str] = None,
    **kwargs,
) -> QuantizedModelInfo:
    """创建量化模型信息"""
    
    if quant_type:
        qt = QuantizationType(quant_type)
    else:
        qt = QuantizationDetector.detect_quant_type(model_path)
    
    config = QuantizationConfig(quant_type=qt, **kwargs)
    
    return QuantizedModelInfo(
        model_path=model_path,
        quant_type=qt,
        bits=config.bits,
    )
