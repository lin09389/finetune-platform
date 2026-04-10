"""
Agent 执行器单元测试
"""

import shutil
import subprocess

import pytest

from agent.core import (
    UnifiedExecutor,
    create_executor,
    get_executor,
)
from agent.core.executor import (
    CompositeOperationHandler,
)
from agent.core.interfaces.types import ExecutionStatus
from agent.operations.base import (
    OperationContext,
    OperationHandler,
    OperationResult,
    OperationStatus,
)
from agent.operations.file.handler import FileOperationHandler
from agent.operations.system_operations import SystemOperationHandler

AgentExecutorNew = UnifiedExecutor


def reset_executor():
    return None


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

    @pytest.mark.asyncio
    async def test_file_write_includes_diff_and_line_stats(self, handler, tmp_path):
        """测试 file_write 返回 diff 和行变更统计"""
        target = tmp_path / "diff_test.txt"
        target.write_text("alpha\nbeta\n", encoding="utf-8")

        result = await handler.run(
            "file_write",
            {
                "path": "diff_test.txt",
                "content": "alpha\ngamma\n",
                "mode": "overwrite",
            },
        )

        assert result.success is True
        assert result.data["path"].endswith("diff_test.txt")
        assert "--- diff_test.txt (before)" in result.data["diff"]
        assert "+++ diff_test.txt (after)" in result.data["diff"]
        assert result.data["added_lines"] >= 1
        assert result.data["removed_lines"] >= 1
        assert "lines" in result.data["summary"]

    @pytest.mark.asyncio
    async def test_file_patch_applies_unified_diff(self, handler, tmp_path):
        """?? `file_patch` ??????? unified diff?"""
        if shutil.which("git") is None:
            pytest.skip("git is required for file_patch test")

        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
        target = tmp_path / "patch_test.txt"
        target.write_text("alpha\nbeta\n", encoding="utf-8")

        patch = "\n".join(
            [
                "--- a/patch_test.txt",
                "+++ b/patch_test.txt",
                "@@ -1,2 +1,2 @@",
                " alpha",
                "-beta",
                "+gamma",
                "",
            ]
        )

        result = await handler.run(
            "file_patch",
            {
                "patch": patch,
            },
        )

        assert result.success is True
        assert "Applied patch" in result.data["summary"]
        assert result.data["applied_files"][0].endswith("patch_test.txt")
        assert target.read_text(encoding="utf-8") == "alpha\ngamma\n"


class TestSystemOperationHandler:
    """系统操作处理器测试"""

    @pytest.fixture
    def handler(self, tmp_path):
        context = OperationContext(workspace=str(tmp_path))
        return SystemOperationHandler(context=context)

    @pytest.mark.asyncio
    async def test_tests_run_extracts_structured_summary(self, handler):
        """测试 tests_run 返回结构化统计和失败明细"""
        result = await handler.run(
            "tests_run",
            {
                "command": [
                    "python",
                    "-c",
                    (
                        "import sys; "
                        "print('FAILED tests/test_chat.py::test_resume - AssertionError: boom'); "
                        "print('=========================== short test summary info ==========================='); "
                        "print('FAILED tests/test_chat.py::test_resume - AssertionError: boom'); "
                        "print('1 failed, 4 passed in 0.12s'); "
                        "sys.exit(1)"
                    ),
                ]
            },
        )

        assert result.success is False
        assert result.data["kind"] == "test_run"
        assert result.data["command"].startswith("python -c")
        assert result.data["returncode"] == 1
        test_summary = result.data["test_summary"]
        assert test_summary["failed"] == 1
        assert test_summary["passed"] == 4
        assert test_summary["framework"] in ("pytest", "unknown")
        assert test_summary["exit_reason"] == "failed"
        assert test_summary["failure_files"] == ["tests/test_chat.py"]
        assert test_summary["failure_cases"][0]["name"] == "tests/test_chat.py::test_resume"
        assert "AssertionError" in test_summary["failure_cases"][0]["message"]


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
