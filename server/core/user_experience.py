"""
用户体验优化模块

功能�?- 配置向导组件
- 环境自动检�?- 配置建议生成
- 一键配置功�?"""
import os
import platform
import subprocess
import logging
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import json
import shutil

logger = logging.getLogger(__name__)


class SystemCapability(str, Enum):
    """系统能力"""
    CUDA = "cuda"
    ROCM = "rocm"
    MPS = "mps"
    CPU = "cpu"
    GPU = "gpu"


@dataclass
class SystemInfo:
    """系统信息"""
    os: str = ""
    os_version: str = ""
    python_version: str = ""
    cpu_count: int = 0
    total_memory_gb: float = 0.0
    available_memory_gb: float = 0.0
    gpu_available: bool = False
    gpu_count: int = 0
    gpu_names: List[str] = field(default_factory=list)
    gpu_memory_gb: List[float] = field(default_factory=list)
    cuda_version: Optional[str] = None
    capabilities: List[SystemCapability] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "os": self.os,
            "os_version": self.os_version,
            "python_version": self.python_version,
            "cpu_count": self.cpu_count,
            "total_memory_gb": self.total_memory_gb,
            "available_memory_gb": self.available_memory_gb,
            "gpu_available": self.gpu_available,
            "gpu_count": self.gpu_count,
            "gpu_names": self.gpu_names,
            "gpu_memory_gb": self.gpu_memory_gb,
            "cuda_version": self.cuda_version,
            "capabilities": [c.value for c in self.capabilities],
        }


@dataclass
class ConfigSuggestion:
    """配置建议"""
    category: str
    name: str
    description: str
    current_value: Any
    suggested_value: Any
    reason: str
    impact: str  # high, medium, low
    auto_applicable: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category,
            "name": self.name,
            "description": self.description,
            "current_value": self.current_value,
            "suggested_value": self.suggested_value,
            "reason": self.reason,
            "impact": self.impact,
            "auto_applicable": self.auto_applicable,
        }


@dataclass
class ConfigWizard:
    """配置向导"""
    step: int = 0
    total_steps: int = 5
    completed: bool = False
    current_step_name: str = ""
    steps: List[str] = field(default_factory=lambda: [
        "welcome",
        "system_check",
        "model_selection",
        "performance_config",
        "final_setup",
    ])
    config: Dict[str, Any] = field(default_factory=dict)
    
    def next_step(self) -> str:
        """进入下一�?""
        if self.step < self.total_steps - 1:
            self.step += 1
            self.current_step_name = self.steps[self.step]
        else:
            self.completed = True
        return self.current_step_name
    
    def previous_step(self) -> str:
        """返回上一�?""
        if self.step > 0:
            self.step -= 1
            self.current_step_name = self.steps[self.step]
        return self.current_step_name
    
    def set_config(self, key: str, value: Any):
        """设置配置"""
        self.config[key] = value
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """获取配置"""
        return self.config.get(key, default)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "step": self.step,
            "total_steps": self.total_steps,
            "completed": self.completed,
            "current_step_name": self.current_step_name,
            "steps": self.steps,
            "config": self.config,
        }


class EnvironmentDetector:
    """
    环境检测器
    
    自动检测系统环境和硬件配置
    """
    
    @staticmethod
    def detect_system() -> SystemInfo:
        """检测系统信�?""
        info = SystemInfo()
        
        info.os = platform.system()
        info.os_version = platform.version()
        
        import sys
        info.python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        info.cpu_count = os.cpu_count()
        
        try:
            import psutil
            mem = psutil.virtual_memory()
            info.total_memory_gb = mem.total / (1024 ** 3)
            info.available_memory_gb = mem.available / (1024 ** 3)
        except ImportError:
            info.total_memory_gb = 8.0
            info.available_memory_gb = 4.0
        
        try:
            import torch
            if torch.cuda.is_available():
                info.gpu_available = True
                info.gpu_count = torch.cuda.device_count()
                info.gpu_names = [
                    torch.cuda.get_device_name(i)
                    for i in range(info.gpu_count)
                ]
                info.gpu_memory_gb = [
                    torch.cuda.get_device_properties(i).total_memory / (1024 ** 3)
                    for i in range(info.gpu_count)
                ]
                info.cuda_version = torch.version.cuda
                info.capabilities.append(SystemCapability.CUDA)
                info.capabilities.append(SystemCapability.GPU)
        except ImportError:
            pass
        
        if not info.gpu_available:
            info.capabilities.append(SystemCapability.CPU)
        
        return info
    
    @staticmethod
    def check_cuda_version() -> Optional[str]:
        """检�?CUDA 版本"""
        try:
            result = subprocess.run(
                ["nvcc", "--version"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                return result.stdout.split()[-1]
        except (FileNotFoundError, subprocess.SubprocessError):
            pass
        return None
    
    @staticmethod
    def check_library_installed(library: str) -> bool:
        """检查库是否安装"""
        try:
            __import__(library)
            return True
        except ImportError:
            return False
    
    @staticmethod
    def get_installed_libraries() -> Dict[str, bool]:
        """获取已安装的�?""
        libraries = [
            "torch", "transformers", "peft", "accelerate",
            "bitsandbytes", "vllm", "auto_gptq", "autoawq",
            "sentence_transformers", "chromadb", "langchain",
        ]
        
        return {
            lib: EnvironmentDetector.check_library_installed(lib)
            for lib in libraries
        }


class ConfigAdvisor:
    """
    配置顾问
    
    基于系统信息生成配置建议
    """
    
    def __init__(self, system_info: Optional[SystemInfo] = None):
        self.system_info = system_info or EnvironmentDetector.detect_system()
    
    def generate_suggestions(self, current_config: Dict[str, Any]) -> List[ConfigSuggestion]:
        """生成配置建议"""
        suggestions = []
        
        suggestions.extend(self._check_gpu_config(current_config))
        suggestions.extend(self._check_memory_config(current_config))
        suggestions.extend(self._check_model_config(current_config))
        suggestions.extend(self._check_library_config(current_config))
        
        return suggestions
    
    def _check_gpu_config(self, config: Dict[str, Any]) -> List[ConfigSuggestion]:
        """检�?GPU 配置"""
        suggestions = []
        
        if self.system_info.gpu_available:
            if config.get("device") == "cpu":
                suggestions.append(ConfigSuggestion(
                    category="device",
                    name="使用 GPU",
                    description="检测到可用 GPU，建议使�?GPU 加�?,
                    current_value="cpu",
                    suggested_value="cuda",
                    reason=f"检测到 {self.system_info.gpu_count} �?GPU: {', '.join(self.system_info.gpu_names)}",
                    impact="high",
                ))
            
            total_gpu_memory = sum(self.system_info.gpu_memory_gb)
            if total_gpu_memory < 8:
                suggestions.append(ConfigSuggestion(
                    category="performance",
                    name="启用量化",
                    description="GPU 显存较小，建议启用量化以减少显存占用",
                    current_value=config.get("quantization", "none"),
                    suggested_value="int4",
                    reason=f"总显�?{total_gpu_memory:.1f}GB < 8GB",
                    impact="high",
                ))
        else:
            if config.get("device") == "cuda":
                suggestions.append(ConfigSuggestion(
                    category="device",
                    name="切换�?CPU",
                    description="未检测到可用 GPU，建议使�?CPU 模式",
                    current_value="cuda",
                    suggested_value="cpu",
                    reason="未检测到 CUDA 设备",
                    impact="high",
                ))
        
        return suggestions
    
    def _check_memory_config(self, config: Dict[str, Any]) -> List[ConfigSuggestion]:
        """检查内存配�?""
        suggestions = []
        
        available_gb = self.system_info.available_memory_gb
        
        if available_gb < 4:
            suggestions.append(ConfigSuggestion(
                category="memory",
                name="减少批处理大�?,
                description="可用内存较少，建议减少批处理大小",
                current_value=config.get("batch_size", 8),
                suggested_value=1,
                reason=f"可用内存 {available_gb:.1f}GB < 4GB",
                impact="medium",
            ))
        
        if available_gb > 16 and config.get("batch_size", 1) < 8:
            suggestions.append(ConfigSuggestion(
                category="memory",
                name="增加批处理大�?,
                description="内存充足，可以增加批处理大小提升性能",
                current_value=config.get("batch_size", 1),
                suggested_value=8,
                reason=f"可用内存 {available_gb:.1f}GB > 16GB",
                impact="medium",
            ))
        
        return suggestions
    
    def _check_model_config(self, config: Dict[str, Any]) -> List[ConfigSuggestion]:
        """检查模型配�?""
        suggestions = []
        
        max_tokens = config.get("max_tokens", 2048)
        if max_tokens > 4096 and not self.system_info.gpu_available:
            suggestions.append(ConfigSuggestion(
                category="model",
                name="减少最�?token �?,
                description="CPU 模式下，建议减少最�?token �?,
                current_value=max_tokens,
                suggested_value=2048,
                reason="CPU 模式处理长序列效率较�?,
                impact="low",
            ))
        
        return suggestions
    
    def _check_library_config(self, config: Dict[str, Any]) -> List[ConfigSuggestion]:
        """检查库配置"""
        suggestions = []
        
        installed = EnvironmentDetector.get_installed_libraries()
        
        if not installed.get("vllm", False) and self.system_info.gpu_available:
            suggestions.append(ConfigSuggestion(
                category="library",
                name="安装 vLLM",
                description="vLLM 可显著提升推理性能",
                current_value="未安�?,
                suggested_value="pip install vllm",
                reason="GPU 可用，vLLM 可提�?2-3x 性能",
                impact="high",
                auto_applicable=False,
            ))
        
        if not installed.get("accelerate", False):
            suggestions.append(ConfigSuggestion(
                category="library",
                name="安装 Accelerate",
                description="Accelerate 可优化大模型加载",
                current_value="未安�?,
                suggested_value="pip install accelerate",
                reason="可优化内存使用和加载速度",
                impact="medium",
                auto_applicable=False,
            ))
        
        return suggestions


class QuickSetup:
    """
    快速设�?    
    一键配置功�?    """
    
    def __init__(self):
        self.system_info = EnvironmentDetector.detect_system()
        self.advisor = ConfigAdvisor(self.system_info)
    
    def auto_configure(self) -> Dict[str, Any]:
        """自动配置"""
        config = {}
        
        if self.system_info.gpu_available:
            config["device"] = "cuda"
            config["use_gpu"] = True
            
            total_memory = sum(self.system_info.gpu_memory_gb)
            if total_memory >= 24:
                config["quantization"] = "none"
                config["batch_size"] = 16
            elif total_memory >= 12:
                config["quantization"] = "int8"
                config["batch_size"] = 8
            elif total_memory >= 8:
                config["quantization"] = "int4"
                config["batch_size"] = 4
            else:
                config["quantization"] = "int4"
                config["batch_size"] = 1
        else:
            config["device"] = "cpu"
            config["use_gpu"] = False
            config["quantization"] = "int8"
            config["batch_size"] = 1
        
        config["max_tokens"] = 2048
        config["flash_attention"] = self.system_info.gpu_available
        config["use_cache"] = True
        
        config["system_info"] = self.system_info.to_dict()
        
        logger.info(f"自动配置完成: {config}")
        
        return config
    
    def get_setup_report(self) -> Dict[str, Any]:
        """获取设置报告"""
        return {
            "system_info": self.system_info.to_dict(),
            "installed_libraries": EnvironmentDetector.get_installed_libraries(),
            "recommendations": [
                s.to_dict() 
                for s in self.advisor.generate_suggestions({})
            ],
        }


_quick_setup: Optional[QuickSetup] = None


def get_quick_setup() -> QuickSetup:
    """获取快速设置单�?""
    global _quick_setup
    if _quick_setup is None:
        _quick_setup = QuickSetup()
    return _quick_setup
