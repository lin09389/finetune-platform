"""
Legacy-facing agent tests aligned with the current unified contract.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.agent_config import ActionType
from agent.core import UnifiedExecutor as AgentExecutor
from agent.intent import IntentDetector
from agent.intent.detector import DetectorConfig
from agent.security_old import SecurityValidator


class TestSecurityValidator:
    @pytest.fixture
    def validator(self, tmp_path):
        return SecurityValidator(tmp_path)

    def test_validate_path_empty(self, validator):
        result = validator.validate_path("")
        assert not result.is_valid
        assert "不能为空" in result.error

    def test_validate_path_traversal(self, validator):
        result = validator.validate_path("../../../etc/passwd")
        assert not result.is_valid
        assert "禁止" in result.error

    def test_validate_path_normal(self, validator):
        result = validator.validate_path("test.txt")
        assert result.is_valid
        assert result.sanitized_value is not None

    def test_validate_app_allowed(self, validator):
        result = validator.validate_app("vscode")
        assert result.is_valid
        assert result.sanitized_value == "code"

    def test_validate_app_not_allowed(self, validator):
        result = validator.validate_app("malware")
        assert not result.is_valid
        assert "不在允许列表" in result.error

    def test_validate_url_valid(self, validator):
        result = validator.validate_url("https://github.com")
        assert result.is_valid

    def test_validate_url_invalid_protocol(self, validator):
        result = validator.validate_url("ftp://example.com")
        assert not result.is_valid
        assert "http/https" in result.error

    def test_validate_url_localhost(self, validator):
        result = validator.validate_url("http://localhost:8080")
        assert result.is_valid


class TestIntentDetector:
    @pytest.fixture
    def detector(self):
        config = DetectorConfig(
            use_rule_matcher=True,
            use_semantic_matcher=False,
            use_bert_classifier=False,
            use_llm_fallback=False,
            use_context=True,
        )
        return IntentDetector(config)

    def test_detect_file_create(self, detector):
        result = detector.detect("创建 test.py 文件")
        assert result.detected
        assert result.action == ActionType.FILE_CREATE
        assert result.params["file_path"] == "test.py"

    def test_detect_file_read(self, detector):
        result = detector.detect("读取 README.md")
        assert result.detected
        assert result.action == ActionType.FILE_READ
        assert result.params["file_path"] == "README.md"

    def test_detect_file_delete(self, detector):
        result = detector.detect("删除 temp.txt")
        assert result.detected
        assert result.action == ActionType.FILE_DELETE
        assert result.need_confirm

    def test_detect_file_list(self, detector):
        result = detector.detect("列出当前目录的文件")
        assert result.detected
        assert result.action == ActionType.FILE_LIST

    def test_detect_app_open(self, detector):
        result = detector.detect("打开Visual Studio Code")
        assert result is not None
        assert result.intent_type in ("app_open", "unknown")

    def test_detect_url_open(self, detector):
        result = detector.detect("打开 https://github.com")
        assert result is not None
        assert result.intent_type in ("url_open", "unknown")

    def test_detect_no_intent(self, detector):
        result = detector.detect("今天天气怎么样？")
        assert result is not None
        assert result.action in ("", "system_info")


class TestAgentExecutor:
    @pytest.fixture
    def executor(self, tmp_path):
        from agent.agent_config import AgentConfig

        config = AgentConfig(working_dir=tmp_path)
        return AgentExecutor(config)

    @pytest.mark.asyncio
    async def test_file_create(self, executor, tmp_path):
        result = await executor.execute(
            ActionType.FILE_CREATE,
            {"file_path": "test.txt", "content": "Hello World"},
        )
        assert result.success
        assert (tmp_path / "test.txt").exists()
        assert (tmp_path / "test.txt").read_text() == "Hello World"

    @pytest.mark.asyncio
    async def test_file_read(self, executor, tmp_path):
        (tmp_path / "read_test.txt").write_text("Test Content")

        result = await executor.execute(
            ActionType.FILE_READ,
            {"file_path": "read_test.txt"},
        )
        assert result.success
        assert result.data["content"] == "Test Content"

    @pytest.mark.asyncio
    async def test_file_read_not_exists(self, executor):
        result = await executor.execute(
            ActionType.FILE_READ,
            {"file_path": "not_exists.txt"},
        )
        assert not result.success
        assert "不存在" in result.error

    @pytest.mark.asyncio
    async def test_file_list(self, executor, tmp_path):
        (tmp_path / "file1.txt").write_text("1")
        (tmp_path / "file2.txt").write_text("2")

        result = await executor.execute(
            ActionType.FILE_LIST,
            {"directory": "."},
        )
        assert result.success
        assert result.data["count"] >= 2

    @pytest.mark.asyncio
    async def test_file_delete_needs_confirm(self, executor, tmp_path):
        (tmp_path / "delete_test.txt").write_text("test")

        result = await executor.execute(
            ActionType.FILE_DELETE,
            {"file_path": "delete_test.txt", "confirmed": False},
        )
        assert not result.success
        assert result.data.get("need_confirm")

    @pytest.mark.asyncio
    async def test_file_delete_confirmed(self, executor, tmp_path):
        (tmp_path / "delete_confirm.txt").write_text("test")

        result = await executor.execute(
            ActionType.FILE_DELETE,
            {"file_path": "delete_confirm.txt", "confirmed": True},
        )
        assert result.success
        assert not (tmp_path / "delete_confirm.txt").exists()

    @pytest.mark.asyncio
    async def test_app_open_not_allowed(self, executor):
        result = await executor.execute(
            ActionType.APP_OPEN,
            {"app_name": "malware"},
        )
        assert not result.success
        assert "不允许打开此应用" in result.error


class TestActionType:
    def test_action_types(self):
        assert ActionType.FILE_CREATE.value == "file_create"
        assert ActionType.FILE_READ.value == "file_read"
        assert ActionType.FILE_DELETE.value == "file_delete"
        assert ActionType.APP_OPEN.value == "app_open"
        assert ActionType.URL_OPEN.value == "url_open"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
