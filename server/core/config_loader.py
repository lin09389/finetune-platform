"""
配置加载器
支持从多种来源加载配置：环境变量、配置文件、命令行参数
"""
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ConfigSource:
    """配置来源"""
    name: str
    priority: int
    data: dict[str, Any] = field(default_factory=dict)


class ConfigLoader:
    """
    配置加载器

    功能：
    - 多来源配置加载
    - 配置优先级管理
    - 配置热重载
    - 配置验证
    """

    def __init__(self, config_dir: str | None = None):
        self.config_dir = Path(config_dir) if config_dir else Path("config")
        self._sources: dict[str, ConfigSource] = {}
        self._config: dict[str, Any] = {}
        self._watchers: list[callable] = []

        self._register_default_sources()

    def _register_default_sources(self):
        """注册默认配置来源"""
        self.register_source("defaults", priority=0, data={})
        self.register_source("env", priority=100, data=self._load_from_env())
        self.register_source("file", priority=50, data={})

    def register_source(self, name: str, priority: int, data: dict[str, Any]):
        """注册配置来源"""
        self._sources[name] = ConfigSource(
            name=name,
            priority=priority,
            data=data
        )
        self._rebuild_config()

    def _load_from_env(self) -> dict[str, Any]:
        """从环境变量加载配置"""
        config = {}

        env_mappings = {
            "HOST": "server.host",
            "PORT": "server.port",
            "LOG_LEVEL": "logging.level",
            "LOG_FORMAT": "logging.format",
            "DATABASE_URL": "database.url",
            "REDIS_URL": "cache.redis_url",
            "SECRET_KEY": "security.secret_key",
            "ALLOWED_ORIGINS": "cors.allowed_origins",
            "MAX_UPLOAD_SIZE": "upload.max_size",
            "RATE_LIMIT": "rate_limit.max_requests",
            "RATE_WINDOW": "rate_limit.window_seconds",
        }

        for env_key, config_key in env_mappings.items():
            value = os.environ.get(env_key)
            if value is not None:
                self._set_nested(config, config_key, self._parse_value(value))

        return config

    def _parse_value(self, value: str) -> Any:
        """解析配置值"""
        if value.lower() in ("true", "yes", "1"):
            return True
        if value.lower() in ("false", "no", "0"):
            return False

        try:
            return int(value)
        except ValueError:
            pass

        try:
            return float(value)
        except ValueError:
            pass

        if "," in value:
            return [v.strip() for v in value.split(",")]

        return value

    def _set_nested(self, config: dict, key: str, value: Any):
        """设置嵌套配置值"""
        keys = key.split(".")
        current = config

        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]

        current[keys[-1]] = value

    def _get_nested(self, config: dict, key: str, default: Any = None) -> Any:
        """获取嵌套配置值"""
        keys = key.split(".")
        current = config

        for k in keys:
            if not isinstance(current, dict) or k not in current:
                return default
            current = current[k]

        return current

    def _rebuild_config(self):
        """重建配置（按优先级合并）"""
        sorted_sources = sorted(
            self._sources.values(),
            key=lambda s: s.priority,
            reverse=True
        )

        self._config = {}
        for source in sorted_sources:
            self._deep_merge(self._config, source.data)

    def _deep_merge(self, base: dict, override: dict):
        """深度合并字典"""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value

    def load_from_file(self, filepath: str, source_name: str = "file"):
        """从文件加载配置"""
        path = Path(filepath)

        if not path.exists():
            logger.warning(f"配置文件不存在: {filepath}")
            return

        try:
            with open(path, encoding='utf-8') as f:
                if path.suffix in ('.json',):
                    data = json.load(f)
                else:
                    data = self._parse_custom_format(f.read())

            if source_name in self._sources:
                self._sources[source_name].data = data
            else:
                self.register_source(source_name, priority=50, data=data)

            logger.info(f"已加载配置文件: {filepath}")

        except Exception as e:
            logger.error(f"加载配置文件失败: {filepath}, 错误: {e}")

    def _parse_custom_format(self, content: str) -> dict[str, Any]:
        """解析自定义格式配置"""
        config = {}

        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()
                self._set_nested(config, key, self._parse_value(value))

        return config

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        return self._get_nested(self._config, key, default)

    def get_all(self) -> dict[str, Any]:
        """获取所有配置"""
        return self._config.copy()

    def set(self, key: str, value: Any, source: str = "runtime"):
        """设置配置值"""
        if source not in self._sources:
            self.register_source(source, priority=200, data={})

        self._set_nested(self._sources[source].data, key, value)
        self._rebuild_config()

        self._notify_watchers(key, value)

    def watch(self, callback: callable):
        """注册配置变更监听器"""
        self._watchers.append(callback)

    def _notify_watchers(self, key: str, value: Any):
        """通知配置变更"""
        for watcher in self._watchers:
            try:
                watcher(key, value)
            except Exception as e:
                logger.error(f"配置监听器错误: {e}")

    def validate(self, schema: dict[str, Any]) -> list[str]:
        """验证配置"""
        errors = []

        for key, rules in schema.items():
            value = self.get(key)

            if rules.get("required", False) and value is None:
                errors.append(f"缺少必需配置: {key}")
                continue

            if value is not None:
                if "type" in rules:
                    expected_type = rules["type"]
                    if not isinstance(value, expected_type):
                        errors.append(f"配置类型错误: {key}, 期望 {expected_type.__name__}")

                if "min" in rules and isinstance(value, (int, float)) and value < rules["min"]:
                        errors.append(f"配置值过小: {key}, 最小值 {rules['min']}")

                if "max" in rules and isinstance(value, (int, float)) and value > rules["max"]:
                        errors.append(f"配置值过大: {key}, 最大值 {rules['max']}")

                if "options" in rules and value not in rules["options"]:
                    errors.append(f"配置值无效: {key}, 可选值 {rules['options']}")

        return errors


_config_loader: ConfigLoader | None = None


def get_config_loader(config_dir: str = None) -> ConfigLoader:
    """获取配置加载器实例"""
    global _config_loader
    if _config_loader is None:
        _config_loader = ConfigLoader(config_dir)
    return _config_loader
