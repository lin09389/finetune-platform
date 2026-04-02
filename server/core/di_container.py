"""
依赖注入容器 - 增强版
支持单例、瞬态、作用域生命周期，以及自动依赖解析
"""
import inspect
import logging
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from threading import Lock
from typing import Any, Generic, TypeVar, get_type_hints

logger = logging.getLogger(__name__)

T = TypeVar('T')
TService = TypeVar('TService')


class ServiceLifetime(str, Enum):
    SINGLETON = "singleton"
    TRANSIENT = "transient"
    SCOPED = "scoped"


@dataclass
class ServiceDescriptor(Generic[T]):
    service_type: type[T]
    implementation: type | None = None
    factory: Callable[['DIContainer'], T] | None = None
    lifetime: ServiceLifetime = ServiceLifetime.SINGLETON
    instance: T | None = None
    dependencies: list[type] = field(default_factory=list)
    on_dispose: Callable[[T], None] | None = None


class ServiceScope:
    """
    服务作用域
    
    在作用域内创建的服务实例会在作用域结束时自动释放
    """

    def __init__(self, container: 'DIContainer'):
        self._container = container
        self._scoped_instances: dict[type, Any] = {}
        self._disposed = False

    def resolve(self, service_type: type[T]) -> T:
        """在作用域内解析服务"""
        if self._disposed:
            raise RuntimeError("作用域已释放")

        descriptor = self._container._get_descriptor(service_type)
        if not descriptor:
            raise KeyError(f"服务未注册: {service_type.__name__}")

        if descriptor.lifetime == ServiceLifetime.SCOPED:
            if service_type in self._scoped_instances:
                return self._scoped_instances[service_type]

            instance = self._container._create_instance(descriptor, self)
            self._scoped_instances[service_type] = instance
            return instance

        return self._container.resolve(service_type)

    def dispose(self):
        """释放作用域内的所有服务"""
        if self._disposed:
            return

        for service_type, instance in self._scoped_instances.items():
            try:
                if hasattr(instance, 'dispose'):
                    instance.dispose()
                elif hasattr(instance, 'close'):
                    instance.close()
            except Exception as e:
                logger.warning(f"释放作用域服务失败 [{service_type.__name__}]: {e}")

        self._scoped_instances.clear()
        self._disposed = True
        logger.debug("服务作用域已释放")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.dispose()
        return False


class DIContainer:
    """
    依赖注入容器
    
    特性:
    - 支持单例、瞬态、作用域生命周期
    - 支持工厂方法注册
    - 支持实例注册
    - 支持自动依赖解析
    - 线程安全
    - 支持服务释放回调
    """

    def __init__(self):
        self._services: dict[type, ServiceDescriptor] = {}
        self._singletons: dict[type, Any] = {}
        self._lock = Lock()
        self._resolving: set = set()

    def register(
        self,
        service_type: type[TService],
        implementation: type[TService] | None = None,
        lifetime: ServiceLifetime = ServiceLifetime.SINGLETON,
        factory: Callable[['DIContainer'], TService] | None = None,
        on_dispose: Callable[[TService], None] | None = None,
    ) -> 'DIContainer':
        """
        注册服务
        
        Args:
            service_type: 服务类型（通常是接口或基类）
            implementation: 实现类型
            lifetime: 生命周期
            factory: 工厂方法
            on_dispose: 释放回调
            
        Returns:
            self (支持链式调用)
        """
        descriptor = ServiceDescriptor(
            service_type=service_type,
            implementation=implementation or service_type,
            lifetime=lifetime,
            factory=factory,
            on_dispose=on_dispose,
        )

        with self._lock:
            self._services[service_type] = descriptor

        logger.debug(f"注册服务: {service_type.__name__} ({lifetime.value})")
        return self

    def register_singleton(
        self,
        service_type: type[TService],
        implementation: type[TService] | None = None,
        factory: Callable[['DIContainer'], TService] | None = None,
    ) -> 'DIContainer':
        """注册单例服务"""
        return self.register(
            service_type,
            implementation,
            ServiceLifetime.SINGLETON,
            factory
        )

    def register_transient(
        self,
        service_type: type[TService],
        implementation: type[TService] | None = None,
        factory: Callable[['DIContainer'], TService] | None = None,
    ) -> 'DIContainer':
        """注册瞬态服务（每次解析创建新实例）"""
        return self.register(
            service_type,
            implementation,
            ServiceLifetime.TRANSIENT,
            factory
        )

    def register_scoped(
        self,
        service_type: type[TService],
        implementation: type[TService] | None = None,
        factory: Callable[['DIContainer'], TService] | None = None,
    ) -> 'DIContainer':
        """注册作用域服务"""
        return self.register(
            service_type,
            implementation,
            ServiceLifetime.SCOPED,
            factory
        )

    def register_instance(
        self,
        service_type: type[TService],
        instance: TService,
        on_dispose: Callable[[TService], None] | None = None,
    ) -> 'DIContainer':
        """
        注册现有实例
        
        Args:
            service_type: 服务类型
            instance: 服务实例
            on_dispose: 释放回调
            
        Returns:
            self
        """
        with self._lock:
            self._singletons[service_type] = instance
            descriptor = ServiceDescriptor(
                service_type=service_type,
                instance=instance,
                lifetime=ServiceLifetime.SINGLETON,
                on_dispose=on_dispose,
            )
            self._services[service_type] = descriptor

        logger.debug(f"注册实例: {service_type.__name__}")
        return self

    def register_factory(
        self,
        service_type: type[TService],
        factory: Callable[['DIContainer'], TService],
        lifetime: ServiceLifetime = ServiceLifetime.SINGLETON,
    ) -> 'DIContainer':
        """
        注册工厂方法
        
        Args:
            service_type: 服务类型
            factory: 工厂方法，接收容器参数
            lifetime: 生命周期
            
        Returns:
            self
        """
        return self.register(
            service_type,
            factory=factory,
            lifetime=lifetime,
        )

    def resolve(self, service_type: type[TService]) -> TService:
        """
        解析服务
        
        Args:
            service_type: 服务类型
            
        Returns:
            服务实例
            
        Raises:
            KeyError: 服务未注册
            RuntimeError: 检测到循环依赖
        """
        descriptor = self._get_descriptor(service_type)
        if not descriptor:
            raise KeyError(f"服务未注册: {service_type.__name__}")

        if service_type in self._resolving:
            raise RuntimeError(f"检测到循环依赖: {service_type.__name__}")

        self._resolving.add(service_type)
        try:
            return self._resolve_descriptor(descriptor)
        finally:
            self._resolving.discard(service_type)

    def _resolve_descriptor(self, descriptor: ServiceDescriptor[T]) -> T:
        """根据描述符解析服务"""
        if descriptor.lifetime == ServiceLifetime.SINGLETON:
            if descriptor.service_type in self._singletons:
                return self._singletons[descriptor.service_type]

            instance = self._create_instance(descriptor)
            with self._lock:
                self._singletons[descriptor.service_type] = instance
            return instance

        if descriptor.lifetime == ServiceLifetime.TRANSIENT:
            return self._create_instance(descriptor)

        raise RuntimeError(
            f"作用域服务需要在作用域内解析: {descriptor.service_type.__name__}"
        )

    def _create_instance(
        self,
        descriptor: ServiceDescriptor[T],
        scope: ServiceScope | None = None,
    ) -> T:
        """创建服务实例"""
        if descriptor.factory:
            try:
                factory_sig = inspect.signature(descriptor.factory)
                if len(factory_sig.parameters) == 0:
                    return descriptor.factory()
            except (TypeError, ValueError):
                pass
            return descriptor.factory(self)

        implementation = descriptor.implementation
        if not implementation:
            raise ValueError(f"服务实现未定义: {descriptor.service_type.__name__}")

        try:
            dependencies = self._resolve_dependencies(implementation)
            instance = implementation(**dependencies)
            return instance
        except Exception as e:
            logger.error(f"创建服务实例失败 [{implementation.__name__}]: {e}")
            raise

    def _resolve_dependencies(self, implementation: type) -> dict[str, Any]:
        """自动解析构造函数依赖"""
        dependencies = {}

        try:
            hints = get_type_hints(implementation.__init__)
        except Exception:
            return dependencies

        sig = inspect.signature(implementation.__init__)

        for param_name, param in sig.parameters.items():
            if param_name == 'self':
                continue

            if param_name == 'container':
                dependencies[param_name] = self
                continue

            if param_name in hints:
                param_type = hints[param_name]

                if self.is_registered(param_type):
                    dependencies[param_name] = self.resolve(param_type)
                elif param.default is not inspect.Parameter.empty:
                    dependencies[param_name] = param.default

        return dependencies

    def _get_descriptor(self, service_type: type) -> ServiceDescriptor | None:
        """获取服务描述符"""
        return self._services.get(service_type)

    def is_registered(self, service_type: type) -> bool:
        """检查服务是否已注册"""
        return service_type in self._services

    def create_scope(self) -> ServiceScope:
        """创建服务作用域"""
        return ServiceScope(self)

    @contextmanager
    def scope(self):
        """作用域上下文管理器"""
        service_scope = self.create_scope()
        try:
            yield service_scope
        finally:
            service_scope.dispose()

    def get_registered_services(self) -> list[type]:
        """获取所有已注册的服务类型"""
        return list(self._services.keys())

    def get_singleton_instances(self) -> dict[type, Any]:
        """获取所有单例实例"""
        return self._singletons.copy()

    def dispose(self):
        """释放所有单例服务"""
        for service_type, instance in list(self._singletons.items()):
            descriptor = self._services.get(service_type)
            if descriptor and descriptor.on_dispose:
                try:
                    descriptor.on_dispose(instance)
                except Exception as e:
                    logger.warning(f"释放服务失败 [{service_type.__name__}]: {e}")
            elif hasattr(instance, 'dispose'):
                try:
                    instance.dispose()
                except Exception as e:
                    logger.warning(f"释放服务失败 [{service_type.__name__}]: {e}")

        self._singletons.clear()
        logger.info("DI 容器已释放所有服务")

    def clear(self):
        """清空容器"""
        self.dispose()
        self._services.clear()
        self._resolving.clear()

    def get_stats(self) -> dict[str, Any]:
        """获取容器统计信息"""
        lifetime_counts = {
            ServiceLifetime.SINGLETON: 0,
            ServiceLifetime.TRANSIENT: 0,
            ServiceLifetime.SCOPED: 0,
        }

        for descriptor in self._services.values():
            lifetime_counts[descriptor.lifetime] += 1

        return {
            "total_services": len(self._services),
            "singleton_instances": len(self._singletons),
            "lifetime_distribution": {
                k.value: v for k, v in lifetime_counts.items()
            },
        }


_container: DIContainer | None = None


def get_container() -> DIContainer:
    """获取全局容器实例"""
    global _container
    if _container is None:
        _container = DIContainer()
    return _container


def reset_container() -> DIContainer:
    """重置容器"""
    global _container
    if _container is not None:
        _container.clear()
    _container = DIContainer()
    return _container


def inject(service_type: type[T]) -> Callable:
    """
    依赖注入装饰器
    
    用法:
        @inject(DatabaseService)
        def my_function(db: DatabaseService):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            if service_type not in kwargs:
                kwargs[service_type.__name__.lower()] = get_container().resolve(service_type)
            return func(*args, **kwargs)
        return wrapper
    return decorator


def setup_core_services():
    """设置核心服务注册"""
    from core.config import get_settings

    container = get_container()

    container.register_singleton(
        type(get_settings()),
        instance=get_settings()
    )

    logger.info("核心服务已注册")
