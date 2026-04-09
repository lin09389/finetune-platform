"""
插件扩展机制

提供插件发现、加载和管理功能
"""
import importlib
import inspect
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path


class PluginState(str, Enum):
    """插件状态"""
    DISCOVERED = "discovered"
    LOADED = "loaded"
    ENABLED = "enabled"
    DISABLED = "disabled"
    ERROR = "error"


@dataclass
class PluginInfo:
    """插件信息"""
    plugin_id: str
    name: str
    version: str
    description: str = ""
    author: str = ""
    plugin_path: str = ""
    state: PluginState = PluginState.DISCOVERED
    loaded_at: datetime | None = None
    error_message: str | None = None
    dependencies: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)


class PluginInterface:
    """插件接口基类"""

    plugin_id: str = ""
    name: str = ""
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    dependencies: list[str] = []
    permissions: list[str] = []

    async def on_load(self) -> None:
        """插件加载时调用"""
        pass

    async def on_enable(self) -> None:
        """插件启用时调用"""
        pass

    async def on_disable(self) -> None:
        """插件禁用时调用"""
        pass

    async def on_unload(self) -> None:
        """插件卸载时调用"""
        pass

    def get_actions(self) -> dict[str, Callable]:
        """获取插件提供的操作"""
        return {}

    def get_parsers(self) -> dict[str, Callable]:
        """获取插件提供的解析器"""
        return {}


class PluginRegistry:
    """插件注册表"""

    def __init__(self):
        self._plugins: dict[str, PluginInfo] = {}
        self._instances: dict[str, PluginInterface] = {}
        self._action_handlers: dict[str, Callable] = {}
        self._parsers: dict[str, Callable] = {}

    def register(self, plugin: PluginInterface) -> None:
        """注册插件"""
        plugin_info = PluginInfo(
            plugin_id=plugin.plugin_id,
            name=plugin.name,
            version=plugin.version,
            description=plugin.description,
            author=plugin.author,
            dependencies=plugin.dependencies,
            permissions=plugin.permissions,
            state=PluginState.LOADED,
            loaded_at=datetime.now(),
        )

        self._plugins[plugin.plugin_id] = plugin_info
        self._instances[plugin.plugin_id] = plugin

        for action_name, handler in plugin.get_actions().items():
            self._action_handlers[action_name] = handler

        for parser_name, parser in plugin.get_parsers().items():
            self._parsers[parser_name] = parser

    def unregister(self, plugin_id: str) -> bool:
        """注销插件"""
        if plugin_id in self._instances:
            plugin = self._instances[plugin_id]

            for action_name in plugin.get_actions().keys():
                self._action_handlers.pop(action_name, None)

            for parser_name in plugin.get_parsers().keys():
                self._parsers.pop(parser_name, None)

            del self._instances[plugin_id]
            del self._plugins[plugin_id]
            return True
        return False

    def get_plugin(self, plugin_id: str) -> PluginInterface | None:
        """获取插件实例"""
        return self._instances.get(plugin_id)

    def get_plugin_info(self, plugin_id: str) -> PluginInfo | None:
        """获取插件信息"""
        return self._plugins.get(plugin_id)

    def get_action_handler(self, action: str) -> Callable | None:
        """获取操作处理器"""
        return self._action_handlers.get(action)

    def get_parser(self, name: str) -> Callable | None:
        """获取解析器"""
        return self._parsers.get(name)

    def list_plugins(self) -> list[PluginInfo]:
        """列出所有插件"""
        return list(self._plugins.values())

    def list_actions(self) -> list[str]:
        """列出所有操作"""
        return list(self._action_handlers.keys())


class PluginLoader:
    """插件加载器"""

    PLUGIN_ENTRY_POINT = "plugin_main"

    def __init__(self, plugin_dirs: list[Path] | None = None):
        self.plugin_dirs = plugin_dirs or [Path("plugins")]
        self._registry = PluginRegistry()

    def discover_plugins(self) -> list[PluginInfo]:
        """发现插件"""
        discovered = []

        for plugin_dir in self.plugin_dirs:
            if not plugin_dir.exists():
                continue

            for path in plugin_dir.iterdir():
                if path.is_dir():
                    plugin_info = self._discover_plugin(path)
                    if plugin_info:
                        discovered.append(plugin_info)
                        self._registry._plugins[plugin_info.plugin_id] = plugin_info

        return discovered

    def _discover_plugin(self, plugin_path: Path) -> PluginInfo | None:
        """发现单个插件"""
        manifest_file = plugin_path / "plugin.json"

        if manifest_file.exists():
            try:
                with open(manifest_file, encoding="utf-8") as f:
                    manifest = json.load(f)

                return PluginInfo(
                    plugin_id=manifest.get("id", plugin_path.name),
                    name=manifest.get("name", plugin_path.name),
                    version=manifest.get("version", "1.0.0"),
                    description=manifest.get("description", ""),
                    author=manifest.get("author", ""),
                    plugin_path=str(plugin_path),
                    dependencies=manifest.get("dependencies", []),
                    permissions=manifest.get("permissions", []),
                    state=PluginState.DISCOVERED,
                )
            except Exception:
                pass

        return PluginInfo(
            plugin_id=plugin_path.name,
            name=plugin_path.name,
            plugin_path=str(plugin_path),
            state=PluginState.DISCOVERED,
        )

    async def load_plugin(self, plugin_id: str) -> bool:
        """加载插件"""
        plugin_info = self._registry.get_plugin_info(plugin_id)
        if not plugin_info:
            return False

        try:
            plugin_path = Path(plugin_info.plugin_path)
            module_name = f"plugins.{plugin_id}"

            spec = importlib.util.spec_from_file_location(
                module_name,
                plugin_path / "__init__.py"
            )

            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                if hasattr(module, self.PLUGIN_ENTRY_POINT):
                    plugin_class = getattr(module, self.PLUGIN_ENTRY_POINT)
                    if inspect.isclass(plugin_class):
                        plugin_instance = plugin_class()

                        if isinstance(plugin_instance, PluginInterface):
                            await plugin_instance.on_load()
                            self._registry.register(plugin_instance)

                            plugin_info.state = PluginState.LOADED
                            plugin_info.loaded_at = datetime.now()
                            return True

            plugin_info.state = PluginState.ERROR
            plugin_info.error_message = "插件入口点未找到"
            return False

        except Exception as e:
            plugin_info.state = PluginState.ERROR
            plugin_info.error_message = str(e)
            return False

    async def unload_plugin(self, plugin_id: str) -> bool:
        """卸载插件"""
        plugin = self._registry.get_plugin(plugin_id)
        if not plugin:
            return False

        try:
            await plugin.on_unload()
            self._registry.unregister(plugin_id)
            return True
        except Exception:
            return False

    async def enable_plugin(self, plugin_id: str) -> bool:
        """启用插件"""
        plugin = self._registry.get_plugin(plugin_id)
        if not plugin:
            return False

        try:
            await plugin.on_enable()
            plugin_info = self._registry.get_plugin_info(plugin_id)
            if plugin_info:
                plugin_info.state = PluginState.ENABLED
            return True
        except Exception:
            return False

    async def disable_plugin(self, plugin_id: str) -> bool:
        """禁用插件"""
        plugin = self._registry.get_plugin(plugin_id)
        if not plugin:
            return False

        try:
            await plugin.on_disable()
            plugin_info = self._registry.get_plugin_info(plugin_id)
            if plugin_info:
                plugin_info.state = PluginState.DISABLED
            return True
        except Exception:
            return False

    def get_registry(self) -> PluginRegistry:
        """获取插件注册表"""
        return self._registry


_plugin_loader: PluginLoader | None = None


def get_plugin_loader() -> PluginLoader:
    """获取插件加载器单例"""
    global _plugin_loader
    if _plugin_loader is None:
        _plugin_loader = PluginLoader()
    return _plugin_loader


__all__ = [
    "PluginState",
    "PluginInfo",
    "PluginInterface",
    "PluginRegistry",
    "PluginLoader",
    "get_plugin_loader",
]
