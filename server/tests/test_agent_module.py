"""
Stable module-level regression tests for the unified agent stack.
"""

import asyncio
import tempfile
from pathlib import Path

import pytest

from agent.agent_config import ActionType, AgentConfig
from agent.audit import AuditLogger
from agent.core import ExecutionResult
from agent.core import UnifiedExecutor as AgentExecutor
from agent.intent.detector import DetectorConfig, IntentDetector
from agent.security_old import SecurityValidator


class TestActionType:
    def test_file_actions(self):
        assert ActionType.FILE_CREATE.value == "file_create"
        assert ActionType.FILE_READ.value == "file_read"
        assert ActionType.FILE_WRITE.value == "file_write"
        assert ActionType.FILE_DELETE.value == "file_delete"
        assert ActionType.FILE_LIST.value == "file_list"

    def test_cua_actions(self):
        assert ActionType.SCREENSHOT.value == "screenshot"
        assert ActionType.MOUSE_CLICK.value == "mouse_click"
        assert ActionType.MOUSE_MOVE.value == "mouse_move"
        assert ActionType.KEYBOARD_TYPE.value == "keyboard_type"
        assert ActionType.WINDOW_LIST.value == "window_list"

    def test_record_actions(self):
        assert ActionType.RECORD_START.value == "record_start"
        assert ActionType.RECORD_STOP.value == "record_stop"
        assert ActionType.RECORD_PLAY.value == "record_play"


class TestAgentConfig:
    def test_default_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = AgentConfig(working_dir=Path(tmpdir))
            assert config.max_file_size > 0
            assert config.enable_confirm is True
            assert config.enable_audit is True

    def test_custom_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = AgentConfig(
                working_dir=Path(tmpdir),
                max_file_size=5 * 1024 * 1024,
                enable_confirm=False,
            )
            assert config.max_file_size == 5 * 1024 * 1024
            assert config.enable_confirm is False

    def test_operation_timeout(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = AgentConfig(working_dir=Path(tmpdir))
            assert config.operation_timeout == 30


class TestSecurityValidator:
    @pytest.fixture
    def validator(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield SecurityValidator(working_dir=Path(tmpdir))

    def test_path_validation_safe(self, validator):
        assert validator.validate_path("test.py").is_valid is True

    def test_path_validation_empty(self, validator):
        assert validator.validate_path("").is_valid is False

    def test_path_validation_blocked(self, validator):
        blocked_paths = [
            "../../../etc/passwd",
            "~/.ssh/id_rsa",
            "/etc/shadow",
            "C:\\Windows\\System32",
        ]
        for path in blocked_paths:
            assert validator.validate_path(path).is_valid is False

    def test_app_validation_allowed(self, validator):
        assert validator.validate_app("vscode").is_valid is True
        assert validator.validate_app("chrome").is_valid is True

    def test_app_validation_blocked(self, validator):
        assert validator.validate_app("unknown_app").is_valid is False

    def test_url_validation(self, validator):
        assert validator.validate_url("https://example.com").is_valid is True
        assert validator.validate_url("ftp://example.com").is_valid is False


class TestAuditLogger:
    def test_log_operation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(log_dir=Path(tmpdir))
            assert logger is not None
            assert len(logger._entries) == 0

    def test_log_session_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(log_dir=Path(tmpdir))
            logger.start_session()
            assert logger._current_session is not None
            logger.end_session()
            assert logger._current_session is None

    def test_get_stats(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(log_dir=Path(tmpdir))
            stats = logger.get_stats()
            assert stats["total"] == 0
            assert stats["success"] == 0
            assert stats["failed"] == 0


class TestAgentExecutor:
    @pytest.fixture
    def executor(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = AgentConfig(working_dir=Path(tmpdir))
            yield AgentExecutor(config=config)

    def test_executor_initialization(self, executor):
        assert executor is not None
        assert executor.config is not None
        assert executor.validator is not None

    def test_execute_file_read_not_found(self, executor):
        result = asyncio.run(executor.execute(
            ActionType.FILE_READ,
            {"file_path": "nonexistent.txt"},
        ))
        assert result.success is False

    def test_execute_screenshot_supported(self, executor):
        result = asyncio.run(executor.execute(
            ActionType.SCREENSHOT,
            {},
        ))
        assert result.success is True

    def test_file_create_and_read(self, executor):
        result = asyncio.run(executor.execute(
            ActionType.FILE_CREATE,
            {"file_path": "test.py", "content": "print('hello')"},
        ))
        assert result.success is True

        result = asyncio.run(executor.execute(
            ActionType.FILE_READ,
            {"file_path": "test.py"},
        ))
        assert result.success is True
        assert "print('hello')" in result.data["content"]

    def test_file_list(self, executor):
        asyncio.run(executor.execute(ActionType.FILE_CREATE, {"file_path": "test1.py", "content": ""}))
        asyncio.run(executor.execute(ActionType.FILE_CREATE, {"file_path": "test2.py", "content": ""}))

        result = asyncio.run(executor.execute(
            ActionType.FILE_LIST,
            {"directory": "."},
        ))
        assert result.success is True
        assert result.data["count"] >= 2


class TestIntentDetection:
    @pytest.fixture
    def detector(self):
        return IntentDetector(DetectorConfig(
            use_rule_matcher=True,
            use_semantic_matcher=False,
            use_bert_classifier=False,
            use_llm_fallback=False,
            use_context=True,
        ))

    def test_screenshot_intent(self, detector):
        result = detector.detect("截图")
        assert result.detected is True
        assert result.action == ActionType.SCREENSHOT

    def test_mouse_position_intent(self, detector):
        result = detector.detect("鼠标在哪里")
        assert result.detected is True
        assert result.action == ActionType.MOUSE_POSITION

    def test_window_list_intent(self, detector):
        result = detector.detect("列出所有窗口")
        assert result.detected is True
        assert result.action == ActionType.WINDOW_LIST

    def test_file_create_intent(self, detector):
        result = detector.detect("创建 test.txt 文件")
        assert result.detected is True
        assert result.action == ActionType.FILE_CREATE

    def test_no_intent(self, detector):
        result = detector.detect("今天天气怎么样")
        assert result is not None


class TestExecutionResult:
    def test_success_result(self):
        result = ExecutionResult(True, message="操作成功", data={"key": "value"})
        assert result.success is True
        assert result.message == "操作成功"
        assert result.data["key"] == "value"
        assert result.error is None

    def test_failure_result(self):
        result = ExecutionResult(False, error="操作失败")
        assert result.success is False
        assert result.error == "操作失败"

    def test_to_dict(self):
        result = ExecutionResult(True, message="测试", data={"a": 1})
        data = result.to_dict()
        assert data["success"] is True
        assert data["message"] == "测试"
        assert data["data"]["a"] == 1
        assert "timestamp" in data
