"""
Agent 模块单元测试
"""
import pytest
from pathlib import Path
import sys

# 添加服务器路�?sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.agent_config import ActionType, ALLOWED_APPS, FORBIDDEN_PATTERNS
from agent.security import SecurityValidator
from agent.intent import IntentDetector
from agent.executor import AgentExecutor, ExecutionResult


class TestSecurityValidator:
    """安全验证器测�?""
    
    @pytest.fixture
    def validator(self, tmp_path):
        return SecurityValidator(tmp_path)
    
    def test_validate_path_empty(self, validator):
        """测试空路�?""
        result = validator.validate_path("")
        assert not result.is_valid
        assert "不能为空" in result.error
    
    def test_validate_path_traversal(self, validator):
        """测试路径遍历攻击"""
        result = validator.validate_path("../../../etc/passwd")
        assert not result.is_valid
        assert "禁止" in result.error
    
    def test_validate_path_normal(self, validator, tmp_path):
        """测试正常路径"""
        result = validator.validate_path("test.txt")
        assert result.is_valid
        assert result.sanitized_value is not None
    
    def test_validate_app_allowed(self, validator):
        """测试允许的应�?""
        result = validator.validate_app("vscode")
        assert result.is_valid
        assert result.sanitized_value == "code"
    
    def test_validate_app_not_allowed(self, validator):
        """测试不允许的应用"""
        result = validator.validate_app("malware")
        assert not result.is_valid
        assert "不允�? in result.error
    
    def test_validate_url_valid(self, validator):
        """测试有效 URL"""
        result = validator.validate_url("https://github.com")
        assert result.is_valid
    
    def test_validate_url_invalid_protocol(self, validator):
        """测试无效协议"""
        result = validator.validate_url("ftp://example.com")
        assert not result.is_valid
        assert "http/https" in result.error
    
    def test_validate_url_localhost(self, validator):
        """测试本地地址"""
        result = validator.validate_url("http://localhost:8080")
        assert not result.is_valid
        assert "禁止" in result.error


class TestIntentDetector:
    """意图检测器测试"""
    
    @pytest.fixture
    def detector(self):
        return IntentDetector()
    
    def test_detect_file_create(self, detector):
        """测试创建文件意图"""
        result = detector.detect("创建 test.py 文件")
        assert result.detected
        assert result.action == ActionType.FILE_CREATE
        assert result.params["file_path"] == "test.py"
    
    def test_detect_file_read(self, detector):
        """测试读取文件意图"""
        result = detector.detect("读取 README.md")
        assert result.detected
        assert result.action == ActionType.FILE_READ
        assert result.params["file_path"] == "README.md"
    
    def test_detect_file_delete(self, detector):
        """测试删除文件意图"""
        result = detector.detect("删除 temp.txt")
        assert result.detected
        assert result.action == ActionType.FILE_DELETE
        assert result.need_confirm  # 删除需要确�?    
    def test_detect_file_list(self, detector):
        """测试列出文件意图"""
        result = detector.detect("列出当前目录的文�?)
        assert result.detected
        assert result.action == ActionType.FILE_LIST
    
    def test_detect_app_open(self, detector):
        """测试打开应用意图"""
        result = detector.detect("打开 VS Code")
        assert result.detected
        assert result.action == ActionType.APP_OPEN
        assert result.params["app_name"] == "vscode"
    
    def test_detect_url_open(self, detector):
        """测试打开网址意图"""
        result = detector.detect("打开 https://github.com")
        assert result.detected
        assert result.action == ActionType.URL_OPEN
        assert result.params["url"] == "https://github.com"
    
    def test_detect_no_intent(self, detector):
        """测试无意图消�?""
        result = detector.detect("今天天气怎么样？")
        assert not result.detected


class TestAgentExecutor:
    """执行器测�?""
    
    @pytest.fixture
    def executor(self, tmp_path):
        from agent.agent_config import AgentConfig
        config = AgentConfig(working_dir=tmp_path)
        return AgentExecutor(config)
    
    @pytest.mark.asyncio
    async def test_file_create(self, executor, tmp_path):
        """测试创建文件"""
        result = await executor.execute(
            ActionType.FILE_CREATE,
            {"file_path": "test.txt", "content": "Hello World"}
        )
        assert result.success
        assert (tmp_path / "test.txt").exists()
        assert (tmp_path / "test.txt").read_text() == "Hello World"
    
    @pytest.mark.asyncio
    async def test_file_read(self, executor, tmp_path):
        """测试读取文件"""
        # 先创建文�?        (tmp_path / "read_test.txt").write_text("Test Content")
        
        result = await executor.execute(
            ActionType.FILE_READ,
            {"file_path": "read_test.txt"}
        )
        assert result.success
        assert result.data["content"] == "Test Content"
    
    @pytest.mark.asyncio
    async def test_file_read_not_exists(self, executor):
        """测试读取不存在的文件"""
        result = await executor.execute(
            ActionType.FILE_READ,
            {"file_path": "not_exists.txt"}
        )
        assert not result.success
        assert "不存�? in result.error
    
    @pytest.mark.asyncio
    async def test_file_list(self, executor, tmp_path):
        """测试列出文件"""
        # 创建一些文�?        (tmp_path / "file1.txt").write_text("1")
        (tmp_path / "file2.txt").write_text("2")
        
        result = await executor.execute(
            ActionType.FILE_LIST,
            {"directory": "."}
        )
        assert result.success
        assert result.data["count"] >= 2
    
    @pytest.mark.asyncio
    async def test_file_delete_needs_confirm(self, executor, tmp_path):
        """测试删除需要确�?""
        (tmp_path / "delete_test.txt").write_text("test")
        
        result = await executor.execute(
            ActionType.FILE_DELETE,
            {"file_path": "delete_test.txt", "confirmed": False}
        )
        assert not result.success
        assert result.data.get("need_confirm")
    
    @pytest.mark.asyncio
    async def test_file_delete_confirmed(self, executor, tmp_path):
        """测试确认删除"""
        (tmp_path / "delete_confirm.txt").write_text("test")
        
        result = await executor.execute(
            ActionType.FILE_DELETE,
            {"file_path": "delete_confirm.txt", "confirmed": True}
        )
        assert result.success
        assert not (tmp_path / "delete_confirm.txt").exists()
    
    @pytest.mark.asyncio
    async def test_app_open_not_allowed(self, executor):
        """测试打开不允许的应用"""
        result = await executor.execute(
            ActionType.APP_OPEN,
            {"app_name": "malware"}
        )
        assert not result.success
        assert "不允�? in result.error


class TestActionType:
    """操作类型枚举测试"""
    
    def test_action_types(self):
        """测试操作类型定义"""
        assert ActionType.FILE_CREATE.value == "file_create"
        assert ActionType.FILE_READ.value == "file_read"
        assert ActionType.FILE_DELETE.value == "file_delete"
        assert ActionType.APP_OPEN.value == "app_open"
        assert ActionType.URL_OPEN.value == "url_open"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
