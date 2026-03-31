"""
Agent 执行器单元测试
"""

import pytest

from agent.core import (
    UnifiedExecutor,
    create_executor,
    get_executor,
)
from agent.core.executor import (
    CompositeOperationHandler,
)
from agent.operations.base import (
    OperationHandler,
    OperationResult,
    OperationContext,
    OperationStatus
)
from agent.core.interfaces.types import ExecutionStatus, ErrorCode
from agent.operations.file.handler import FileOperationHandler
AgentExecutorNew = UnifiedExecutor
reset_executor = lambda: None


class TestOperationResult:
    """操作结果测试"""

    def test_ok_result(self):
        """测试成功结果"""
        result = OperationResult.ok("操作成功", {"key": "value"})

        assert result.success is True
        assert result.status == OperationStatus.SUCCESS
        assert result.message == "操作成功"
        assert result.data["key"] == "value"

    def test_fail_result(self):
        """测试失败结果"""
        from agent.core.interfaces import ErrorCode
        result = OperationResult.fail(error="操作失败", error_code=ErrorCode.INTERNAL_ERROR)

        assert result.success is False
        assert result.status == ExecutionStatus.FAILED
        assert result.error == "操作失败"
        assert result.error_code == ErrorCode.INTERNAL_ERROR

    def test_partial_result(self):
        """测试部分成功结果"""
        result = OperationResult.partial("部分成功")

        assert result.success is True
        assert result.status == OperationStatus.PARTIAL

    def test_to_dict(self):
        """测试转字典"""
        result = OperationResult.ok("测试")
        data = result.to_dict()

        assert data["success"] is True
        assert data["message"] == "测试"


class TestOperationContext:
    """操作上下文测试"""

    def test_create_context(self):
        """测试创建上下文"""
        context = OperationContext(workspace="/tmp")

        assert context.workspace == "/tmp"
        assert context.timeout == 300

    def test_has_permission(self):
        """测试权限检查"""
        context = OperationContext(
            workspace="/tmp",
            permissions=["read", "write"]
        )

        assert context.has_permission("read") is True
        assert context.has_permission("execute") is False

    def test_has_wildcard_permission(self):
        """测试通配符权限"""
        context = OperationContext(
            workspace="/tmp",
            permissions=["*"]
        )

        assert context.has_permission("any_permission") is True

    def test_require_permission(self):
        """测试要求权限"""
        context = OperationContext(
            workspace="/tmp",
            permissions=["read"]
        )

        context.require_permission("read")

        with pytest.raises(PermissionError):
            context.require_permission("write")


class TestFileOperationHandler:
    """文件操作处理器测试"""

    @pytest.fixture
    def handler(self, tmp_path):
        context = OperationContext(workspace=str(tmp_path))
        return FileOperationHandler(context=context)

    def test_get_supported_actions(self, handler):
        """测试获取支持的操作"""
        actions = handler.get_supported_actions()

        assert "file_create" in actions
        assert "file_read" in actions
        assert "file_write" in actions
        assert "file_delete" in actions

    @pytest.mark.asyncio
    async def test_file_create(self, handler, tmp_path):
        """测试创建文件"""
        result = await handler.run("file_create", {
            "path": "test.txt",
            "content": "Hello World"
        })

        assert result.success is True
        assert (tmp_path / "test.txt").exists()

    @pytest.mark.asyncio
    async def test_file_read(self, handler, tmp_path):
        """测试读取文件"""
        test_file = tmp_path / "read_test.txt"
        test_file.write_text("Test content")

        result = await handler.run("file_read", {
            "path": "read_test.txt"
        })

        assert result.success is True
        assert result.data["content"] == "Test content"

    @pytest.mark.asyncio
    async def test_file_read_not_found(self, handler):
        """测试读取不存在的文件"""
        result = await handler.run("file_read", {
            "path": "nonexistent.txt"
        })

        assert result.success is False
        assert result.error_code == "FILE_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_file_delete(self, handler, tmp_path):
        """测试删除文件"""
        test_file = tmp_path / "delete_test.txt"
        test_file.write_text("To be deleted")

        result = await handler.run("file_delete", {
            "path": "delete_test.txt"
        })

        assert result.success is True
        assert not test_file.exists()

    @pytest.mark.asyncio
    async def test_dir_create_and_list(self, handler, tmp_path):
        """测试创建和列出目录"""
        await handler.run("dir_create", {"path": "test_dir"})

        result = await handler.run("dir_list", {"path": "test_dir"})

        assert result.success is True
        assert result.data["count"] == 0


class TestCompositeOperationHandler:
    """组合操作处理器测试"""

    @pytest.fixture
    def composite_handler(self, tmp_path):
        context = OperationContext(workspace=str(tmp_path))
        file_handler = FileOperationHandler(context=context)
        return CompositeOperationHandler(handlers=[file_handler], context=context)

    def test_get_supported_actions(self, composite_handler):
        """测试获取支持的操作"""
        actions = composite_handler.get_supported_actions()

        assert len(actions) > 0
        assert "file_create" in actions

    @pytest.mark.asyncio
    async def test_route_to_handler(self, composite_handler, tmp_path):
        """测试路由到处理器"""
        result = await composite_handler.run("file_create", {
            "path": "routed.txt",
            "content": "Routed content"
        })

        assert result.success is True
        assert (tmp_path / "routed.txt").exists()

    @pytest.mark.asyncio
    async def test_unsupported_action(self, composite_handler):
        """测试不支持的操作"""
        result = await composite_handler.run("unsupported_action", {})

        assert result.success is False
        assert result.error_code == "UNSUPPORTED_ACTION"


class TestAgentExecutorNew:
    """Agent 执行器测试"""

    @pytest.fixture
    def executor(self, tmp_path):
        return create_executor(workspace=str(tmp_path))

    def test_create_executor(self, executor):
        """测试创建执行器"""
        assert executor is not None
        assert len(executor.get_supported_actions()) > 0

    def test_get_supported_actions(self, executor):
        """测试获取支持的操作"""
        actions = executor.get_supported_actions()

        assert "file_create" in actions
        assert "mouse_click" in actions
        assert "process_list" in actions

    @pytest.mark.asyncio
    async def test_execute_file_operation(self, executor):
        """测试执行文件操作"""
        result = await executor.execute("file_create", {
            "path": "executor_test.txt",
            "content": "Test content"
        })

        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_batch(self, executor):
        """测试批量执行"""
        operations = [
            {"action": "file_create", "params": {"path": "batch1.txt", "content": "1"}},
            {"action": "file_create", "params": {"path": "batch2.txt", "content": "2"}},
        ]

        results = await executor.execute_batch(operations)

        assert len(results) == 2
        assert all(r.success for r in results)

    def test_get_stats(self, executor):
        """测试获取统计"""
        stats = executor.get_stats()

        assert "execution_count" in stats
        assert "supported_actions_count" in stats

    def test_register_handler(self, executor):
        """测试注册处理器"""
        class CustomHandler(OperationHandler):
            def get_supported_actions(self):
                return ["custom_action"]

            async def execute(self, action, params):
                return OperationResult.ok("Custom action executed")

        executor.register_handler(CustomHandler())

        assert "custom_action" in executor.get_supported_actions()


class TestAgentExecutorSingleton:
    """Agent 执行器单例测试"""

    def test_get_executor(self):
        """测试获取执行器单例"""
        executor1 = get_executor()
        executor2 = get_executor()

        assert executor1 is executor2

    def test_reset_executor(self):
        """测试重置执行器"""
        executor1 = get_executor()
        executor2 = reset_executor()

        assert executor1 is not executor2
