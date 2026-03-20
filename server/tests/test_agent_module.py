"""
Agent 模块单元测试
"""
import pytest
import tempfile
import asyncio
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from agent.agent_config import ActionType, AgentConfig
from agent.executor import AgentExecutor, ExecutionResult
from agent.security import SecurityValidator, ValidationResult
from agent.audit import AuditLogger


class TestActionType:
    """测试 ActionType 枚举"""
    
    def test_file_actions(self):
        """测试文件操作类型"""
        assert ActionType.FILE_CREATE.value == "file_create"
        assert ActionType.FILE_READ.value == "file_read"
        assert ActionType.FILE_WRITE.value == "file_write"
        assert ActionType.FILE_DELETE.value == "file_delete"
        assert ActionType.FILE_LIST.value == "file_list"
    
    def test_cua_actions(self):
        """测试 CUA 操作类型"""
        assert ActionType.SCREENSHOT.value == "screenshot"
        assert ActionType.MOUSE_CLICK.value == "mouse_click"
        assert ActionType.MOUSE_MOVE.value == "mouse_move"
        assert ActionType.KEYBOARD_TYPE.value == "keyboard_type"
        assert ActionType.WINDOW_LIST.value == "window_list"
    
    def test_record_actions(self):
        """测试录制操作类型"""
        assert ActionType.RECORD_START.value == "record_start"
        assert ActionType.RECORD_STOP.value == "record_stop"
        assert ActionType.RECORD_PLAY.value == "record_play"


class TestAgentConfig:
    """测试 Agent 配置"""
    
    def test_default_config(self):
        """测试默认配置"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = AgentConfig(working_dir=Path(tmpdir))
            assert config.max_file_size > 0
            assert config.enable_confirm is True
            assert config.enable_audit is True
    
    def test_custom_config(self):
        """测试自定义配�?""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = AgentConfig(
                working_dir=Path(tmpdir),
                max_file_size=5 * 1024 * 1024,
                enable_confirm=False
            )
            assert config.max_file_size == 5 * 1024 * 1024
            assert config.enable_confirm is False
    
    def test_operation_timeout(self):
        """测试操作超时配置"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = AgentConfig(working_dir=Path(tmpdir))
            assert config.operation_timeout == 30


class TestSecurityValidator:
    """测试安全验证�?""
    
    @pytest.fixture
    def validator(self):
        """创建验证器实�?""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield SecurityValidator(working_dir=Path(tmpdir))
    
    def test_path_validation_safe(self, validator):
        """测试安全路径验证"""
        result = validator.validate_path("test.py")
        assert result.is_valid is True
    
    def test_path_validation_empty(self, validator):
        """测试空路径验�?""
        result = validator.validate_path("")
        assert result.is_valid is False
    
    def test_path_validation_blocked(self, validator):
        """测试禁止路径验证"""
        blocked_paths = [
            "../../../etc/passwd",
            "~/.ssh/id_rsa",
            "/etc/shadow",
            "C:\\Windows\\System32",
        ]
        for path in blocked_paths:
            result = validator.validate_path(path)
            assert result.is_valid is False, f"Path should be blocked: {path}"
    
    def test_extension_validation_create(self, validator):
        """测试创建文件扩展名验�?""
        result = validator.validate_path("test.py", ActionType.FILE_CREATE)
        assert result.is_valid is True
        
        result = validator.validate_path("test.txt", ActionType.FILE_CREATE)
        assert result.is_valid is True
        
        result = validator.validate_path("test.json", ActionType.FILE_CREATE)
        assert result.is_valid is True
    
    def test_extension_validation_read(self, validator):
        """测试读取文件扩展名验�?""
        result = validator.validate_path("test.log", ActionType.FILE_READ)
        assert result.is_valid is True
        
        result = validator.validate_path("test.png", ActionType.FILE_READ)
        assert result.is_valid is True
    
    def test_app_validation_allowed(self, validator):
        """测试允许的应用验�?""
        result = validator.validate_app("vscode")
        assert result.is_valid is True
        
        result = validator.validate_app("chrome")
        assert result.is_valid is True
        
        result = validator.validate_app("notepad")
        assert result.is_valid is True
    
    def test_app_validation_blocked(self, validator):
        """测试禁止的应用验�?""
        result = validator.validate_app("unknown_app")
        assert result.is_valid is False
    
    def test_url_validation_safe(self, validator):
        """测试安全 URL 验证"""
        result = validator.validate_url("https://example.com")
        assert result.is_valid is True
        
        result = validator.validate_url("http://example.com/path")
        assert result.is_valid is True
    
    def test_url_validation_blocked(self, validator):
        """测试禁止�?URL 验证"""
        result = validator.validate_url("ftp://example.com")
        assert result.is_valid is False
        
        result = validator.validate_url("javascript:alert(1)")
        assert result.is_valid is False
    
    def test_content_validation(self, validator):
        """测试内容验证"""
        safe_content = "print('hello')"
        result = validator.validate_content(safe_content)
        assert result.is_valid is True
        
        large_content = "x" * (20 * 1024 * 1024)
        result = validator.validate_content(large_content)
        assert result.is_valid is False
    
    def test_is_dangerous_action(self, validator):
        """测试危险操作检�?""
        assert validator.is_dangerous_action(ActionType.FILE_DELETE) is True
        assert validator.is_dangerous_action(ActionType.FILE_READ) is False


class TestAuditLogger:
    """测试审计日志"""
    
    def test_log_operation(self):
        """测试操作日志"""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(log_dir=Path(tmpdir))
            assert logger is not None
            assert len(logger._entries) == 0
    
    def test_log_error(self):
        """测试错误日志"""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(log_dir=Path(tmpdir))
            logger.start_session()
            assert logger._current_session is not None
            logger.end_session()
            assert logger._current_session is None
    
    def test_get_stats(self):
        """测试统计信息"""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(log_dir=Path(tmpdir))
            stats = logger.get_stats()
            assert stats["total"] == 0
            assert stats["success"] == 0
            assert stats["failed"] == 0
    
    def test_get_recent_entries(self):
        """测试获取最近条�?""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(log_dir=Path(tmpdir))
            entries = logger.get_recent_entries()
            assert isinstance(entries, list)


class TestAgentExecutor:
    """测试 Agent 执行�?""
    
    @pytest.fixture
    def executor(self):
        """创建执行器实�?""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = AgentConfig(working_dir=Path(tmpdir))
            yield AgentExecutor(config=config)
    
    def test_executor_initialization(self, executor):
        """测试执行器初始化"""
        assert executor is not None
        assert executor.config is not None
        assert executor.validator is not None
    
    def test_execute_file_read_not_found(self, executor):
        """测试读取不存在的文件"""
        result = asyncio.run(executor.execute(
            ActionType.FILE_READ,
            {"file_path": "nonexistent.txt"}
        ))
        assert result.success is False
    
    def test_execute_invalid_action(self, executor):
        """测试无效操作 - CUA 操作不在执行器支持列表中"""
        result = asyncio.run(executor.execute(
            ActionType.SCREENSHOT,
            {}
        ))
        assert result.success is False
    
    def test_file_create_and_read(self, executor):
        """测试创建和读取文�?""
        result = asyncio.run(executor.execute(
            ActionType.FILE_CREATE,
            {"file_path": "test.py", "content": "print('hello')"}
        ))
        assert result.success is True
        
        result = asyncio.run(executor.execute(
            ActionType.FILE_READ,
            {"file_path": "test.py"}
        ))
        assert result.success is True
        assert "print('hello')" in result.data["content"]
    
    def test_file_list(self, executor):
        """测试列出文件"""
        asyncio.run(executor.execute(
            ActionType.FILE_CREATE,
            {"file_path": "test1.py", "content": ""}
        ))
        asyncio.run(executor.execute(
            ActionType.FILE_CREATE,
            {"file_path": "test2.py", "content": ""}
        ))
        
        result = asyncio.run(executor.execute(
            ActionType.FILE_LIST,
            {"directory": "."}
        ))
        assert result.success is True
        assert result.data["count"] >= 2


class TestIntentDetection:
    """测试意图检�?""
    
    def test_screenshot_intent(self):
        """测试截图意图"""
        from agent.intent.detector import IntentDetector
        detector = IntentDetector()
        
        result = detector.detect("帮我截个�?)
        assert result.detected is True
        assert result.action == ActionType.SCREENSHOT
    
    def test_mouse_position_intent(self):
        """测试鼠标位置意图"""
        from agent.intent.detector import IntentDetector
        detector = IntentDetector()
        
        result = detector.detect("鼠标在哪�?)
        assert result.detected is True
        assert result.action == ActionType.MOUSE_POSITION
    
    def test_window_list_intent(self):
        """测试窗口列表意图"""
        from agent.intent.detector import IntentDetector
        detector = IntentDetector()
        
        result = detector.detect("列出所有窗�?)
        assert result.detected is True
        assert result.action == ActionType.WINDOW_LIST
    
    def test_file_create_intent(self):
        """测试文件创建意图"""
        from agent.intent.detector import IntentDetector
        detector = IntentDetector()
        
        result = detector.detect("创建 test.txt 文件")
        assert result.detected is True
        assert result.action == ActionType.FILE_CREATE
    
    def test_no_intent(self):
        """测试无意�?""
        from agent.intent.detector import IntentDetector
        detector = IntentDetector()
        
        result = detector.detect("今天天气怎么�?)
        assert result.detected is False


class TestExecutionResult:
    """测试执行结果"""
    
    def test_success_result(self):
        """测试成功结果"""
        result = ExecutionResult(True, message="操作成功", data={"key": "value"})
        assert result.success is True
        assert result.message == "操作成功"
        assert result.data["key"] == "value"
        assert result.error is None
    
    def test_failure_result(self):
        """测试失败结果"""
        result = ExecutionResult(False, error="操作失败")
        assert result.success is False
        assert result.error == "操作失败"
    
    def test_to_dict(self):
        """测试转换为字�?""
        result = ExecutionResult(True, message="测试", data={"a": 1})
        d = result.to_dict()
        assert d["success"] is True
        assert d["message"] == "测试"
        assert d["data"]["a"] == 1
        assert "timestamp" in d
