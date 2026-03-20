"""
配置加载�?- 支持 YAML 配置文件
"""
import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from functools import lru_cache
import logging

logger = logging.getLogger(__name__)


class ConfigLoader:
    """配置加载�?""
    
    _instance = None
    _config: Dict[str, Any] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._config_dir = Path(__file__).parent.parent / "config"
            self._load_all_configs()
            self._initialized = True
    
    def _load_all_configs(self):
        """加载所有配置文�?""
        if not self._config_dir.exists():
            logger.warning(f"配置目录不存�? {self._config_dir}")
            return
        
        for config_file in self._config_dir.glob("*.yaml"):
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    config_name = config_file.stem
                    self._config[config_name] = yaml.safe_load(f) or {}
                    logger.info(f"加载配置文件: {config_file.name}")
            except Exception as e:
                logger.error(f"加载配置文件失败 {config_file}: {e}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置�?        
        支持点号分隔的嵌套键，如 "inference.model_cache.max_size"
        """
        keys = key.split(".")
        value = self._config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def get_section(self, section: str) -> Dict[str, Any]:
        """获取配置�?""
        return self._config.get(section, {})
    
    def reload(self):
        """重新加载配置"""
        self._config.clear()
        self._load_all_configs()
    
    @property
    def inference(self) -> Dict[str, Any]:
        """推理配置"""
        return self._config.get("inference", {})
    
    @property
    def knowledge(self) -> Dict[str, Any]:
        """知识库配�?""
        return self._config.get("knowledge", {})
    
    @property
    def memory(self) -> Dict[str, Any]:
        """记忆配置"""
        return self._config.get("memory", {})
    
    @property
    def chat(self) -> Dict[str, Any]:
        """对话配置"""
        return self._config.get("chat", {})


_config_loader: Optional[ConfigLoader] = None


def get_config_loader() -> ConfigLoader:
    """获取配置加载器单�?""
    global _config_loader
    if _config_loader is None:
        _config_loader = ConfigLoader()
    return _config_loader


def get_config(key: str, default: Any = None) -> Any:
    """获取配置值的便捷函数"""
    return get_config_loader().get(key, default)
