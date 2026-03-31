"""
DI 容器单元测试
"""

import pytest

from core.di_container import (
    DIContainer,
    ServiceScope,
    get_container,
    reset_container,
)


class TestService:
    """测试服务"""
    def __init__(self, name: str = "default"):
        self.name = name
        self.initialized = True


class TestServiceWithDependency:
    """带依赖的测试服务"""
    def __init__(self, dependency: TestService):
        self.dependency = dependency


class TestDisposableService:
    """可释放的测试服务"""
    def __init__(self):
        self.disposed = False

    def dispose(self):
        self.disposed = True


class TestDIContainer:
    """DI 容器测试"""

    def test_create_container(self):
        """测试创建容器"""
        container = DIContainer()
        assert container is not None
        assert len(container.get_registered_services()) == 0

    def test_register_singleton(self):
        """测试注册单例服务"""
        container = DIContainer()

        container.register_singleton(TestService, lambda: TestService("singleton"))

        services = container.get_registered_services()
        assert TestService in services

    def test_register_transient(self):
        """测试注册瞬态服务"""
        container = DIContainer()

        container.register_transient(TestService, lambda: TestService("transient"))

        instance1 = container.resolve(TestService)
        instance2 = container.resolve(TestService)

        assert instance1 is not instance2

    def test_register_scoped(self):
        """测试注册作用域服务"""
        container = DIContainer()

        container.register_scoped(TestService, lambda: TestService("scoped"))

        with container.scope() as scope:
            instance1 = scope.resolve(TestService)
            instance2 = scope.resolve(TestService)

            assert instance1 is instance2

    def test_resolve_singleton(self):
        """测试解析单例服务"""
        container = DIContainer()

        container.register_singleton(TestService, lambda: TestService("test"))

        instance1 = container.resolve(TestService)
        instance2 = container.resolve(TestService)

        assert instance1 is instance2
        assert instance1.name == "test"

    def test_resolve_transient(self):
        """测试解析瞬态服务"""
        container = DIContainer()

        call_count = [0]

        def factory():
            call_count[0] += 1
            return TestService(f"instance_{call_count[0]}")

        container.register_transient(TestService, factory)

        instance1 = container.resolve(TestService)
        instance2 = container.resolve(TestService)

        assert instance1 is not instance2
        assert call_count[0] == 2

    def test_register_instance(self):
        """测试注册实例"""
        container = DIContainer()

        instance = TestService("existing")
        container.register_instance(TestService, instance)

        resolved = container.resolve(TestService)

        assert resolved is instance

    def test_is_registered(self):
        """测试检查服务是否已注册"""
        container = DIContainer()

        assert not container.is_registered(TestService)

        container.register_singleton(TestService, lambda: TestService())

        assert container.is_registered(TestService)

    def test_resolve_unregistered_service(self):
        """测试解析未注册的服务"""
        container = DIContainer()

        with pytest.raises(KeyError):
            container.resolve(TestService)

    def test_create_scope(self):
        """测试创建作用域"""
        container = DIContainer()

        scope = container.create_scope()

        assert scope is not None
        assert isinstance(scope, ServiceScope)

    def test_scope_context_manager(self):
        """测试作用域上下文管理器"""
        container = DIContainer()
        container.register_scoped(TestService, lambda: TestService("scoped"))

        with container.scope() as scope:
            instance = scope.resolve(TestService)
            assert instance.name == "scoped"

    def test_dispose_services(self):
        """测试释放服务"""
        container = DIContainer()

        container.register(
            TestDisposableService,
            factory=lambda: TestDisposableService(),
            on_dispose=lambda s: s.dispose()
        )

        instance = container.resolve(TestDisposableService)
        assert not instance.disposed

        container.dispose()

        assert instance.disposed

    def test_get_stats(self):
        """测试获取统计信息"""
        container = DIContainer()

        container.register_singleton(TestService, lambda: TestService())
        container.register_transient(str, lambda: "test")

        stats = container.get_stats()

        assert stats["total_services"] == 2
        assert stats["lifetime_distribution"]["singleton"] == 1
        assert stats["lifetime_distribution"]["transient"] == 1


class TestServiceScope:
    """服务作用域测试"""

    def test_scope_isolation(self):
        """测试作用域隔离"""
        container = DIContainer()
        container.register_scoped(TestService, lambda: TestService("scoped"))

        with container.scope() as scope1:
            instance1 = scope1.resolve(TestService)

        with container.scope() as scope2:
            instance2 = scope2.resolve(TestService)

        assert instance1 is not instance2

    def test_scope_dispose(self):
        """测试作用域释放"""
        container = DIContainer()
        container.register_scoped(TestDisposableService, lambda: TestDisposableService())

        with container.scope() as scope:
            instance = scope.resolve(TestDisposableService)
            assert not instance.disposed

        assert instance.disposed


class TestDIContainerSingleton:
    """DI 容器单例测试"""

    def test_get_container(self):
        """测试获取容器单例"""
        container1 = get_container()
        container2 = get_container()

        assert container1 is container2

    def test_reset_container(self):
        """测试重置容器"""
        container1 = get_container()
        container1.register_singleton(TestService, lambda: TestService())

        container2 = reset_container()

        assert container1 is not container2
        assert not container2.is_registered(TestService)
