from collections.abc import Callable
from enum import Enum
from typing import Any, TypeVar

from ..container import DependencyContainer, ServiceLifetime
from ..interfaces import BaseExecutor, BaseFeedback, BaseParser, BasePermissionController
from ..types import ModuleInfo

T = TypeVar("T")


class ModuleType(str, Enum):
    PARSER = "parser"
    PERMISSION = "permission"
    EXECUTOR = "executor"
    FEEDBACK = "feedback"


class ModuleState(str, Enum):
    REGISTERED = "registered"
    LOADED = "loaded"
    ACTIVE = "active"
    DISABLED = "disabled"
    ERROR = "error"


class ModuleRegistry:
    def __init__(self, container: DependencyContainer | None = None):
        self._container = container or DependencyContainer()
        self._modules: dict[str, ModuleInfo] = {}
        self._module_states: dict[str, ModuleState] = {}
        self._module_instances: dict[str, Any] = {}
        self._module_factories: dict[str, Callable] = {}
        self._parsers: dict[str, type[BaseParser]] = {}
        self._permissions: dict[str, type[BasePermissionController]] = {}
        self._executors: dict[str, type[BaseExecutor]] = {}
        self._feedbacks: dict[str, type[BaseFeedback]] = {}
        self._action_mapping: dict[str, str] = {}

    def register_module(
        self,
        module_type: ModuleType,
        name: str,
        implementation: type,
        info: ModuleInfo | None = None,
        lifetime: ServiceLifetime = ServiceLifetime.SINGLETON,
    ) -> "ModuleRegistry":
        module_key = f"{module_type.value}:{name}"

        if info is None:
            info = ModuleInfo(name=name)
        self._modules[module_key] = info
        self._module_states[module_key] = ModuleState.REGISTERED

        match module_type:
            case ModuleType.PARSER:
                self._parsers[name] = implementation
                self._container.register_singleton(BaseParser, implementation)
            case ModuleType.PERMISSION:
                self._permissions[name] = implementation
                self._container.register_singleton(BasePermissionController, implementation)
            case ModuleType.EXECUTOR:
                self._executors[name] = implementation
                self._container.register_singleton(BaseExecutor, implementation)
                self._register_actions(name, implementation)
            case ModuleType.FEEDBACK:
                self._feedbacks[name] = implementation
                self._container.register_singleton(BaseFeedback, implementation)

        return self

    def _register_actions(self, executor_name: str, executor_class: type[BaseExecutor]) -> None:
        try:
            temp_instance = executor_class()
            actions = temp_instance.get_supported_actions()
            for action in actions:
                self._action_mapping[action] = executor_name
        except Exception:
            pass

    def register_parser(
        self,
        name: str,
        parser_class: type[BaseParser],
        info: ModuleInfo | None = None,
    ) -> "ModuleRegistry":
        return self.register_module(ModuleType.PARSER, name, parser_class, info)

    def register_permission(
        self,
        name: str,
        permission_class: type[BasePermissionController],
        info: ModuleInfo | None = None,
    ) -> "ModuleRegistry":
        return self.register_module(ModuleType.PERMISSION, name, permission_class, info)

    def register_executor(
        self,
        name: str,
        executor_class: type[BaseExecutor],
        info: ModuleInfo | None = None,
    ) -> "ModuleRegistry":
        return self.register_module(ModuleType.EXECUTOR, name, executor_class, info)

    def register_feedback(
        self,
        name: str,
        feedback_class: type[BaseFeedback],
        info: ModuleInfo | None = None,
    ) -> "ModuleRegistry":
        return self.register_module(ModuleType.FEEDBACK, name, feedback_class, info)

    def get_parser(self, name: str) -> BaseParser | None:
        if name not in self._parsers:
            return None
        return self._container.resolve(BaseParser)

    def get_permission_controller(self, name: str) -> BasePermissionController | None:
        if name not in self._permissions:
            return None
        return self._container.resolve(BasePermissionController)

    def get_executor(self, name: str) -> BaseExecutor | None:
        if name not in self._executors:
            return None
        return self._container.resolve(BaseExecutor)

    def get_executor_for_action(self, action: str) -> BaseExecutor | None:
        executor_name = self._action_mapping.get(action)
        if not executor_name:
            return None
        return self.get_executor(executor_name)

    def get_feedback(self, name: str) -> BaseFeedback | None:
        if name not in self._feedbacks:
            return None
        return self._container.resolve(BaseFeedback)

    def get_all_parsers(self) -> dict[str, type[BaseParser]]:
        return self._parsers.copy()

    def get_all_permissions(self) -> dict[str, type[BasePermissionController]]:
        return self._permissions.copy()

    def get_all_executors(self) -> dict[str, type[BaseExecutor]]:
        return self._executors.copy()

    def get_all_feedbacks(self) -> dict[str, type[BaseFeedback]]:
        return self._feedbacks.copy()

    def get_module_info(self, module_type: ModuleType, name: str) -> ModuleInfo | None:
        module_key = f"{module_type.value}:{name}"
        return self._modules.get(module_key)

    def get_module_state(self, module_type: ModuleType, name: str) -> ModuleState | None:
        module_key = f"{module_type.value}:{name}"
        return self._module_states.get(module_key)

    def set_module_state(
        self, module_type: ModuleType, name: str, state: ModuleState
    ) -> "ModuleRegistry":
        module_key = f"{module_type.value}:{name}"
        if module_key in self._modules:
            self._module_states[module_key] = state
        return self

    def get_supported_actions(self) -> list[str]:
        return list(self._action_mapping.keys())

    def unregister_module(self, module_type: ModuleType, name: str) -> bool:
        module_key = f"{module_type.value}:{name}"
        if module_key not in self._modules:
            return False

        del self._modules[module_key]
        del self._module_states[module_key]

        match module_type:
            case ModuleType.PARSER:
                if name in self._parsers:
                    del self._parsers[name]
            case ModuleType.PERMISSION:
                if name in self._permissions:
                    del self._permissions[name]
            case ModuleType.EXECUTOR:
                if name in self._executors:
                    executor_class = self._executors[name]
                    del self._executors[name]
                    self._unregister_actions(executor_class)
            case ModuleType.FEEDBACK:
                if name in self._feedbacks:
                    del self._feedbacks[name]

        return True

    def _unregister_actions(self, executor_class: type[BaseExecutor]) -> None:
        try:
            temp_instance = executor_class()
            actions = temp_instance.get_supported_actions()
            for action in actions:
                if action in self._action_mapping:
                    del self._action_mapping[action]
        except Exception:
            pass

    def clear(self) -> None:
        self._modules.clear()
        self._module_states.clear()
        self._module_instances.clear()
        self._module_factories.clear()
        self._parsers.clear()
        self._permissions.clear()
        self._executors.clear()
        self._feedbacks.clear()
        self._action_mapping.clear()
        self._container.clear_all()


registry = ModuleRegistry()
