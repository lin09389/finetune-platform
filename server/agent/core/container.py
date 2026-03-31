from collections.abc import Callable
from enum import Enum
from typing import Any, TypeVar

T = TypeVar("T")


class ServiceLifetime(str, Enum):
    SINGLETON = "singleton"
    TRANSIENT = "transient"
    SCOPED = "scoped"


class ServiceDescriptor:
    def __init__(
        self,
        service_type: type,
        implementation: type | Callable | None = None,
        lifetime: ServiceLifetime = ServiceLifetime.SINGLETON,
        factory: Callable | None = None,
    ):
        self.service_type = service_type
        self.implementation = implementation or service_type
        self.lifetime = lifetime
        self.factory = factory
        self.instance: Any = None


class DependencyContainer:
    def __init__(self):
        self._services: dict[type, ServiceDescriptor] = {}
        self._singletons: dict[type, Any] = {}
        self._scoped_instances: dict[type, Any] = {}

    def register(
        self,
        service_type: type[T],
        implementation: type[T] | None = None,
        lifetime: ServiceLifetime = ServiceLifetime.SINGLETON,
    ) -> "DependencyContainer":
        descriptor = ServiceDescriptor(
            service_type=service_type,
            implementation=implementation or service_type,
            lifetime=lifetime,
        )
        self._services[service_type] = descriptor
        return self

    def register_singleton(
        self, service_type: type[T], implementation: type[T] | None = None
    ) -> "DependencyContainer":
        return self.register(service_type, implementation, ServiceLifetime.SINGLETON)

    def register_transient(
        self, service_type: type[T], implementation: type[T] | None = None
    ) -> "DependencyContainer":
        return self.register(service_type, implementation, ServiceLifetime.TRANSIENT)

    def register_scoped(
        self, service_type: type[T], implementation: type[T] | None = None
    ) -> "DependencyContainer":
        return self.register(service_type, implementation, ServiceLifetime.SCOPED)

    def register_factory(
        self,
        service_type: type[T],
        factory: Callable[["DependencyContainer"], T],
        lifetime: ServiceLifetime = ServiceLifetime.SINGLETON,
    ) -> "DependencyContainer":
        descriptor = ServiceDescriptor(
            service_type=service_type,
            lifetime=lifetime,
            factory=factory,
        )
        self._services[service_type] = descriptor
        return self

    def register_instance(self, service_type: type[T], instance: T) -> "DependencyContainer":
        self._singletons[service_type] = instance
        descriptor = ServiceDescriptor(
            service_type=service_type,
            lifetime=ServiceLifetime.SINGLETON,
        )
        self._services[service_type] = descriptor
        return self

    def resolve(self, service_type: type[T]) -> T:
        if service_type not in self._services:
            raise KeyError(f"Service {service_type.__name__} is not registered")

        descriptor = self._services[service_type]

        if descriptor.lifetime == ServiceLifetime.SINGLETON:
            if service_type in self._singletons:
                return self._singletons[service_type]
            instance = self._create_instance(descriptor)
            self._singletons[service_type] = instance
            return instance

        if descriptor.lifetime == ServiceLifetime.SCOPED:
            if service_type in self._scoped_instances:
                return self._scoped_instances[service_type]
            instance = self._create_instance(descriptor)
            self._scoped_instances[service_type] = instance
            return instance

        return self._create_instance(descriptor)

    def _create_instance(self, descriptor: ServiceDescriptor) -> Any:
        if descriptor.factory:
            return descriptor.factory(self)

        implementation = descriptor.implementation
        if isinstance(implementation, type):
            return implementation()
        return implementation

    def is_registered(self, service_type: type) -> bool:
        return service_type in self._services

    def clear_scoped(self) -> None:
        self._scoped_instances.clear()

    def clear_all(self) -> None:
        self._services.clear()
        self._singletons.clear()
        self._scoped_instances.clear()

    def get_registered_services(self) -> list[type]:
        return list(self._services.keys())


DIContainer = DependencyContainer

container = DependencyContainer()
