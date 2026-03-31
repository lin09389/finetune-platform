"""
安全模块单元测试
测试安全路径检查、危险命令检测、安全操作判断等关键功能
"""
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.agent_config import ActionType
from agent.friendly_errors import (
    ErrorCategory,
    categorize_error,
    format_error_message,
    get_friendly_error,
)
from agent.safety_assessor import (
    SafetyAssessor,
    SafetyLevel,
    assess_safety,
    is_safe_action,
)


class TestSafetyAssessor:
    """安全评估器测试"""

    @pytest.fixture
    def assessor(self):
        return SafetyAssessor()

    def test_safe_action_identification(self, assessor):
        """测试安全操作识别"""
        safe_actions = [
            ActionType.FILE_READ,
            ActionType.FILE_LIST,
            ActionType.SCREENSHOT,
            ActionType.WINDOW_LIST,
            ActionType.OCR_RECOGNIZE,
        ]

        for action in safe_actions:
            assert is_safe_action(action), f"{action.value} 应该是安全操作"

    def test_dangerous_action_identification(self, assessor):
        """测试危险操作识别"""
        dangerous_actions = [
            ActionType.FILE_DELETE,
            ActionType.MOUSE_CLICK,
            ActionType.KEYBOARD_HOTKEY,
            ActionType.WINDOW_CLOSE,
        ]

        for action in dangerous_actions:
            assert not is_safe_action(action), f"{action.value} 应该是危险操作"

    def test_file_delete_requires_confirmation(self, assessor):
        """测试文件删除需要确认"""
        assessment = assess_safety(ActionType.FILE_DELETE, {"file_path": "test.txt"})

        assert assessment.level == SafetyLevel.DANGEROUS
        assert assessment.requires_confirmation is True
        assert "删除" in assessment.reason

    def test_file_read_is_safe(self, assessor):
        """测试文件读取是安全的"""
        assessment = assess_safety(ActionType.FILE_READ, {"file_path": "test.txt"})

        assert assessment.level == SafetyLevel.SAFE
        assert assessment.is_safe is True
        assert assessment.requires_confirmation is False

    def test_sensitive_file_detection(self, assessor):
        """测试敏感文件检测"""
        sensitive_files = [
            ".env",
            "id_rsa",
            "credentials.json",
            "private.key",
        ]

        for filename in sensitive_files:
            assessment = assess_safety(
                ActionType.FILE_WRITE,
                {"file_path": filename}
            )
            assert assessment.level == SafetyLevel.DANGEROUS, f"{filename} 应该被识别为敏感文件"

    def test_dangerous_url_detection(self, assessor):
        """测试危险URL检测"""
        dangerous_urls = [
            "http://localhost:8080",
            "http://127.0.0.1:3000",
            "http://192.168.1.1",
            "file:///etc/passwd",
        ]

        for url in dangerous_urls:
            assessment = assess_safety(
                ActionType.URL_OPEN,
                {"url": url}
            )
            assert assessment.level == SafetyLevel.DANGEROUS, f"{url} 应该被识别为危险URL"

    def test_safe_url_allowed(self, assessor):
        """测试安全URL允许"""
        safe_urls = [
            "https://www.google.com",
            "https://github.com",
        ]

        for url in safe_urls:
            assessment = assess_safety(
                ActionType.URL_OPEN,
                {"url": url}
            )
            assert assessment.level == SafetyLevel.CAUTION, f"{url} 应该是注意级别"


class TestFriendlyErrors:
    """友好错误信息测试"""

    def test_file_not_found_error(self):
        """测试文件不存在错误"""
        error = get_friendly_error("file_not_found")

        assert error.category == ErrorCategory.FILE_NOT_FOUND
        assert "文件" in error.message or "不存在" in error.title
        assert len(error.solutions) > 0

    def test_unsafe_path_error(self):
        """测试不安全路径错误"""
        error = get_friendly_error("unsafe_path")

        assert error.category == ErrorCategory.UNSAFE_PATH
        assert "安全" in error.message

    def test_error_categorization(self):
        """测试错误分类"""
        test_cases = [
            ("File not found", "file_not_found"),
            ("Permission denied", "file_access_denied"),
            ("Timeout error", "timeout"),
            ("Unsafe path detected", "unsafe_path"),
        ]

        for error_message, expected_category in test_cases:
            category = categorize_error(error_message)
            assert category == expected_category, f"'{error_message}' 应该分类为 {expected_category}"

    def test_format_error_message(self):
        """测试错误消息格式化"""
        message = format_error_message("file_not_found", "test.txt 不存在")

        assert "文件不存在" in message
        assert "建议" in message or "解决方案" in message.lower() or len(message) > 50


class TestFileExecutorSafety:
    """文件执行器安全测试"""

    @pytest.fixture
    def executor(self, tmp_path):
        from agent.operations.file.handler import FileOperationHandler as FileExecutor
        return FileExecutor(workspace=str(tmp_path))

    def test_safe_path_validation(self, executor, tmp_path):
        """测试安全路径验证"""
        safe_paths = [
            tmp_path / "test.txt",
            tmp_path / "subdir" / "file.txt",
        ]

        for path in safe_paths:
            assert executor._is_safe_path(path), f"{path} 应该是安全路径"

    def test_dangerous_path_rejection(self, executor):
        """测试危险路径拒绝"""
        dangerous_paths = [
            Path("/etc/passwd"),
            Path("C:\\Windows\\System32\\config\\SAM"),
            Path("/root/.ssh/id_rsa"),
        ]

        for path in dangerous_paths:
            assert not executor._is_safe_path(path), f"{path} 应该被拒绝"

    def test_path_traversal_prevention(self, executor, tmp_path):
        """测试路径遍历防护"""
        traversal_paths = [
            "../../../etc/passwd",
            "..\\..\\..\\Windows\\System32",
        ]

        for path_str in traversal_paths:
            path = executor._resolve_path(path_str)
            assert not executor._is_safe_path(path), f"路径遍历应该被阻止: {path_str}"


class TestIntentDetection:
    """意图检测测试"""

    @pytest.fixture
    def detector(self):
        from agent.intent.unified_interface import get_unified_detector
        return get_unified_detector()

    def test_file_create_detection(self, detector):
        """测试文件创建检测"""
        test_cases = [
            "创建test.txt",
            "新建一个文件config.json",
            "生成README.md文件",
        ]

        for text in test_cases:
            result = detector.detect(text)
            assert result.detected, f"应该检测到意图: {text}"
            assert result.action == ActionType.FILE_CREATE

    def test_file_write_detection(self, detector):
        """测试文件写入检测"""
        test_cases = [
            "把test.txt改成Hello",
            "将config.json内容改为{}",
            "修改main.py的代码",
        ]

        for text in test_cases:
            result = detector.detect(text)
            assert result.detected, f"应该检测到意图: {text}"
            assert result.action == ActionType.FILE_WRITE

    def test_file_delete_detection(self, detector):
        """测试文件删除检测"""
        test_cases = [
            "删除test.txt",
            "移除old_file.txt",
        ]

        for text in test_cases:
            result = detector.detect(text)
            assert result.detected, f"应该检测到意图: {text}"
            assert result.action == ActionType.FILE_DELETE
            assert result.need_confirm is True

    def test_batch_delete_detection(self, detector):
        """测试批量删除检测"""
        test_cases = [
            "批量删除tmp文件",
            "删除所有log文件",
            "清理tmp文件",
        ]

        for text in test_cases:
            result = detector.detect(text)
            assert result.detected, f"应该检测到意图: {text}"
            assert result.action == ActionType.FILE_BATCH_DELETE

    def test_screenshot_detection(self, detector):
        """测试截图检测"""
        test_cases = [
            "截图",
            "截屏",
            "截取屏幕",
        ]

        for text in test_cases:
            result = detector.detect(text)
            assert result.detected, f"应该检测到意图: {text}"
            assert result.action == ActionType.SCREENSHOT

    def test_multi_intent_detection(self, detector):
        """测试多意图检测"""
        text = "创建test.txt 然后写入Hello"
        results = detector.detect_multi(text)

        assert len(results) >= 1, "应该检测到至少一个意图"


class TestExecutionMonitor:
    """执行监控测试"""

    @pytest.fixture
    def monitor(self):
        from agent.execution_monitor import ExecutionMonitor
        with tempfile.TemporaryDirectory() as tmpdir:
            yield ExecutionMonitor(storage_path=tmpdir)

    def test_record_success(self, monitor):
        """测试成功记录"""
        from agent.execution_monitor import ExecutionStatus

        monitor.record(
            action="file_read",
            status=ExecutionStatus.SUCCESS,
            duration_ms=100.0
        )

        stats = monitor.get_stats("file_read")
        assert stats["total_count"] == 1
        assert stats["success_count"] == 1
        assert stats["success_rate"] == 100.0

    def test_record_failure(self, monitor):
        """测试失败记录"""
        from agent.execution_monitor import ExecutionStatus

        monitor.record(
            action="file_delete",
            status=ExecutionStatus.FAILURE,
            duration_ms=50.0,
            error="文件不存在",
            error_category="file_not_found"
        )

        stats = monitor.get_stats("file_delete")
        assert stats["total_count"] == 1
        assert stats["failure_count"] == 1
        assert "file_not_found" in stats["error_categories"]

    def test_success_rate_calculation(self, monitor):
        """测试成功率计算"""
        from agent.execution_monitor import ExecutionStatus

        for i in range(10):
            status = ExecutionStatus.SUCCESS if i < 8 else ExecutionStatus.FAILURE
            monitor.record(
                action="test_action",
                status=status,
                duration_ms=100.0
            )

        stats = monitor.get_stats("test_action")
        assert stats["success_rate"] == 80.0

    def test_alert_generation(self, monitor):
        """测试告警生成"""
        from agent.execution_monitor import ExecutionStatus

        for i in range(15):
            status = ExecutionStatus.SUCCESS if i < 5 else ExecutionStatus.FAILURE
            monitor.record(
                action="failing_action",
                status=status,
                duration_ms=100.0
            )

        alerts = monitor.get_alerts()
        assert len(alerts) > 0, "成功率过低应该生成告警"


class TestProgressTracker:
    """进度追踪测试"""

    @pytest.fixture
    def tracker(self):
        from agent.progress_tracker import ProgressTracker
        return ProgressTracker()

    def test_create_task(self, tracker):
        """测试创建任务"""
        from agent.progress_tracker import ProgressStatus

        info = tracker.create_task("test-1", "测试操作", total_steps=10)

        assert info.task_id == "test-1"
        assert info.action == "测试操作"
        assert info.status == ProgressStatus.PENDING
        assert info.total_steps == 10

    def test_update_progress(self, tracker):
        """测试更新进度"""
        tracker.create_task("test-2", "测试操作")
        tracker.start_task("test-2")

        tracker.update_progress("test-2", progress=50.0, message="进度一半")

        info = tracker.get_progress("test-2")
        assert info.progress == 50.0
        assert "一半" in info.message

    def test_complete_task(self, tracker):
        """测试完成任务"""
        from agent.progress_tracker import ProgressStatus

        tracker.create_task("test-3", "测试操作")
        tracker.start_task("test-3")
        tracker.complete_task("test-3", "完成")

        info = tracker.get_progress("test-3")
        assert info.status == ProgressStatus.COMPLETED
        assert info.progress == 100.0

    def test_cancel_task(self, tracker):
        """测试取消任务"""
        from agent.progress_tracker import ProgressStatus

        tracker.create_task("test-4", "测试操作")
        tracker.cancel_task("test-4")

        assert tracker.is_cancelled("test-4")
        info = tracker.get_progress("test-4")
        assert info.status == ProgressStatus.CANCELLED


class TestFeedbackManager:
    """反馈管理器测试"""

    @pytest.fixture
    def feedback_manager(self, tmp_path):
        from agent.feedback_manager import FeedbackManager
        return FeedbackManager(storage_path=str(tmp_path))

    def test_submit_positive_feedback(self, feedback_manager):
        """测试提交正面反馈"""
        from agent.feedback_manager import FeedbackCategory, FeedbackType

        feedback = feedback_manager.submit_feedback(
            feedback_type=FeedbackType.POSITIVE,
            category=FeedbackCategory.EXECUTION_RESULT,
            rating=5,
            comment="操作非常顺利",
            action="file_read",
            execution_success=True,
        )

        assert feedback.feedback_id is not None
        assert feedback.feedback_type == FeedbackType.POSITIVE
        assert feedback.rating == 5
        assert feedback.execution_success is True

    def test_submit_negative_feedback(self, feedback_manager):
        """测试提交负面反馈"""
        from agent.feedback_manager import FeedbackCategory, FeedbackType

        feedback = feedback_manager.submit_feedback(
            feedback_type=FeedbackType.NEGATIVE,
            category=FeedbackCategory.INTENT_DETECTION,
            rating=2,
            comment="意图识别错误",
            action="file_write",
            intent_detected="file_read",
            intent_correct=False,
            suggested_intent="file_write",
        )

        assert feedback.feedback_type == FeedbackType.NEGATIVE
        assert feedback.intent_correct is False
        assert feedback.suggested_intent == "file_write"

    def test_feedback_stats(self, feedback_manager):
        """测试反馈统计"""
        from agent.feedback_manager import FeedbackCategory, FeedbackType

        for i in range(10):
            feedback_manager.submit_feedback(
                feedback_type=FeedbackType.POSITIVE if i < 7 else FeedbackType.NEGATIVE,
                category=FeedbackCategory.EXECUTION_RESULT,
                rating=5 if i < 7 else 2,
                execution_success=i < 7,
            )

        stats = feedback_manager.get_stats(days=1)

        assert stats.total_feedback == 10
        assert stats.positive_count == 7
        assert stats.negative_count == 3
        assert stats.execution_success_rate == 70.0

    def test_intent_corrections(self, feedback_manager):
        """测试意图纠正"""
        from agent.feedback_manager import FeedbackCategory, FeedbackType

        feedback_manager.submit_feedback(
            feedback_type=FeedbackType.NEGATIVE,
            category=FeedbackCategory.INTENT_DETECTION,
            rating=2,
            intent_detected="file_read",
            intent_correct=False,
            suggested_intent="file_write",
        )

        corrections = feedback_manager.get_intent_corrections()

        assert len(corrections) == 1
        assert corrections[0]["detected_intent"] == "file_read"
        assert corrections[0]["correct_intent"] == "file_write"

    def test_improvement_suggestions(self, feedback_manager):
        """测试改进建议"""
        from agent.feedback_manager import FeedbackCategory, FeedbackType

        feedback_manager.submit_feedback(
            feedback_type=FeedbackType.IMPROVEMENT,
            category=FeedbackCategory.USER_EXPERIENCE,
            rating=3,
            suggested_improvement="希望能支持更多文件格式",
        )

        suggestions = feedback_manager.get_improvement_suggestions()

        assert len(suggestions) == 1
        assert "文件格式" in suggestions[0]["suggestion"]


class TestHelpSystem:
    """帮助系统测试"""

    @pytest.fixture
    def help_system(self):
        from agent.help_system import HelpSystem
        return HelpSystem()

    def test_get_command_help(self, help_system):
        """测试获取命令帮助"""
        from agent.help_system import HelpCategory

        cmd = help_system.get_command_help("读取文件")

        assert cmd is not None
        assert cmd.command == "读取文件"
        assert "读取" in cmd.description
        assert len(cmd.examples) > 0
        assert cmd.category == HelpCategory.FILE_OPERATIONS

    def test_search_commands(self, help_system):
        """测试搜索命令"""
        results = help_system.search("文件")

        assert len(results) > 0
        assert any("文件" in cmd.command for cmd in results)

    def test_get_category_commands(self, help_system):
        """测试获取类别命令"""
        from agent.help_system import HelpCategory

        commands = help_system.get_category_commands(HelpCategory.FILE_OPERATIONS)

        assert len(commands) > 0
        assert all(cmd.category == HelpCategory.FILE_OPERATIONS for cmd in commands)

    def test_format_command_help(self, help_system):
        """测试格式化命令帮助"""
        text = help_system.format_command_help("读取文件")

        assert "读取文件" in text
        assert "示例" in text
        assert "提示" in text

    def test_format_overview(self, help_system):
        """测试格式化概览"""
        text = help_system.format_overview()

        assert "帮助" in text
        assert "文件操作" in text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
