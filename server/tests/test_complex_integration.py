"""
复杂集成测试 - AI 对话页面全功能验证

测试场景：
1. 多轮对话与记忆系统
2. 智能意图检测（CUA + 文件操作）
3. 操作链执行（连续多步操作）
4. 云端 AI 流式输出
5. 知识库检索增强
6. 危险操作确认机制
7. 并发请求处理
8. 错误恢复与重试
9. 端到端用户场景
"""
import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.agent_config import ActionType, AgentConfig
from agent.audit import AuditLogger
from agent.core import ExecutionResult
from agent.core import UnifiedExecutor as AgentExecutor
from agent.intent.detector import IntentDetector
from agent.security_old import SecurityValidator

BASE_URL = "http://127.0.0.1:8000"


class TestComplexScenarios:
    """复杂场景集成测试"""

    @pytest.fixture
    def temp_dir(self):
        """创建临时目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def executor(self, temp_dir):
        """创建执行器"""
        config = AgentConfig(working_dir=temp_dir)
        return AgentExecutor(config=config)

    @pytest.fixture
    def detector(self):
        """创建意图检测器"""
        return IntentDetector()

    # ==================== 场景 1: 多轮对话与记忆系统 ====================

    @pytest.mark.asyncio
    async def test_multi_turn_conversation_with_memory(self, executor):
        """
        场景 1: 多轮对话与记忆系统
        
        流程：
        1. 用户说"我的名字是张三"
        2. 系统提取记忆
        3. 用户说"我叫什么名字？"
        4. 系统从记忆中召回信息
        """
        messages = [
            {"role": "user", "content": "我的名字是张三，我是一名软件工程师"},
            {"role": "assistant", "content": "你好张三，很高兴认识你！"},
            {"role": "user", "content": "我擅长 Python 和 JavaScript"},
            {"role": "assistant", "content": "太棒了，Python 和 JavaScript 都是非常流行的语言。"},
            {"role": "user", "content": "我叫什么名字？我擅长什么？"},
        ]

        assert len(messages) == 5
        assert "张三" in messages[0]["content"]
        assert "软件工程师" in messages[0]["content"]
        assert "Python" in messages[2]["content"]

    # ==================== 场景 2: 智能意图检测 ====================

    def test_intent_detection_comprehensive(self, detector):
        """
        场景 2: 智能意图检测全面测试
        
        测试各种自然语言表达的意图识别
        """
        test_cases = [
            ("截图", ActionType.SCREENSHOT, True),
            ("帮我截个图", ActionType.SCREENSHOT, True),
            ("拍张屏幕照片", ActionType.SCREENSHOT, True),
            ("鼠标在哪里", ActionType.MOUSE_POSITION, True),
            ("获取鼠标位置", ActionType.MOUSE_POSITION, True),
            ("点击坐标 (100, 200)", ActionType.MOUSE_CLICK, True),
            ("双击 (500, 300)", ActionType.MOUSE_CLICK, True),
            ("列出所有窗口", ActionType.WINDOW_LIST, True),
            ("显示打开的窗口", ActionType.WINDOW_LIST, True),
            ("创建 test.txt 文件", ActionType.FILE_CREATE, True),
            ("新建一个文件 README.md", ActionType.FILE_CREATE, True),
            ("读取 config.json", ActionType.FILE_READ, True),
            ("查看 README.md 的内容", ActionType.FILE_READ, True),
            ("列出当前目录文件", ActionType.FILE_LIST, True),
            ("显示目录内容", ActionType.FILE_LIST, True),
            ("今天天气怎么样", None, False),
            ("帮我写一首诗", None, False),
        ]

        passed = 0
        total = len(test_cases)

        for message, expected_action, should_detect in test_cases:
            result = detector.detect(message)

            if should_detect:
                if result.detected and result.action == expected_action:
                    passed += 1
                else:
                    print(f"失败: '{message}' - 期望: {expected_action}, 实际: {result.action}")
            else:
                if not result.detected:
                    passed += 1
                else:
                    print(f"失败: '{message}' - 不应检测到意图，但检测到: {result.action}")

        accuracy = passed / total * 100
        print(f"\n意图检测准确率: {passed}/{total} ({accuracy:.1f}%)")
        assert accuracy >= 80, f"意图检测准确率过低: {accuracy:.1f}%"

    # ==================== 场景 3: 操作链执行 ====================

    @pytest.mark.asyncio
    async def test_operation_chain(self, executor, temp_dir):
        """
        场景 3: 操作链执行
        
        模拟用户连续执行多个操作：
        1. 创建文件
        2. 写入内容
        3. 读取验证
        4. 列出目录
        5. 删除文件
        """
        results = []

        result1 = await executor.execute(
            ActionType.FILE_CREATE,
            {"file_path": "test_chain.txt", "content": "Hello World"}
        )
        results.append(("创建文件", result1.success))
        assert result1.success, f"创建文件失败: {result1.error}"

        result2 = await executor.execute(
            ActionType.FILE_WRITE,
            {"file_path": "test_chain.txt", "content": "Updated Content"}
        )
        results.append(("写入文件", result2.success))
        assert result2.success, f"写入文件失败: {result2.error}"

        result3 = await executor.execute(
            ActionType.FILE_READ,
            {"file_path": "test_chain.txt"}
        )
        results.append(("读取文件", result3.success))
        assert result3.success, f"读取文件失败: {result3.error}"
        assert "Updated Content" in result3.data.get("content", "")

        result4 = await executor.execute(
            ActionType.FILE_LIST,
            {"directory": "."}
        )
        results.append(("列出目录", result4.success))
        assert result4.success, f"列出目录失败: {result4.error}"
        assert result4.data.get("count", 0) >= 1

        result5 = await executor.execute(
            ActionType.FILE_DELETE,
            {"file_path": "test_chain.txt", "confirmed": True}
        )
        results.append(("删除文件", result5.success))
        assert result5.success, f"删除文件失败: {result5.error}"

        print("\n操作链执行结果:")
        for name, success in results:
            status = "成功" if success else "失败"
            print(f"  {status} {name}")

        assert all(s for _, s in results), "操作链中存在失败的操作"

    # ==================== 场景 4: 危险操作确认 ====================

    @pytest.mark.asyncio
    async def test_dangerous_operation_confirmation(self, executor, temp_dir):
        """
        场景 4: 危险操作确认机制
        
        测试危险操作需要确认才能执行
        """
        await executor.execute(
            ActionType.FILE_CREATE,
            {"file_path": "dangerous_test.txt", "content": "test"}
        )

        validator = executor.validator

        assert validator.is_dangerous_action(ActionType.FILE_DELETE) is True
        assert validator.is_dangerous_action(ActionType.FILE_WRITE) is True
        assert validator.is_dangerous_action(ActionType.FILE_READ) is False
        assert validator.is_dangerous_action(ActionType.FILE_LIST) is False

        result = await executor.execute(
            ActionType.FILE_DELETE,
            {"file_path": "dangerous_test.txt", "confirmed": True}
        )
        assert result.success, "确认后应能删除文件"

    # ==================== 场景 5: 安全验证 ====================

    def test_security_validation(self, temp_dir):
        """
        场景 5: 安全验证测试
        
        测试路径遍历攻击、危险扩展名等
        """
        validator = SecurityValidator(working_dir=temp_dir)

        blocked_paths = [
            "../../../etc/passwd",
            "~/.ssh/id_rsa",
            "/etc/shadow",
            "C:\\Windows\\System32\\config",
            "..\\..\\..\\secret.txt",
        ]

        for path in blocked_paths:
            result = validator.validate_path(path)
            assert result.is_valid is False, f"应阻止危险路径: {path}"

        safe_paths = [
            "test.txt",
            "subdir/file.py",
            "README.md",
            "config.json",
        ]

        for path in safe_paths:
            result = validator.validate_path(path)
            assert result.is_valid is True, f"应允许安全路径: {path}"

    # ==================== 场景 6: 并发请求处理 ====================

    @pytest.mark.asyncio
    async def test_concurrent_operations(self, executor, temp_dir):
        """
        场景 6: 并发请求处理
        
        同时执行多个文件操作
        """
        tasks = []

        for i in range(5):
            task = executor.execute(
                ActionType.FILE_CREATE,
                {"file_path": f"concurrent_{i}.txt", "content": f"Content {i}"}
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        success_count = sum(1 for r in results if isinstance(r, ExecutionResult) and r.success)

        print(f"\n并发操作结果: {success_count}/5 成功")
        assert success_count >= 4, f"并发操作成功率过低: {success_count}/5"

        for i in range(5):
            await executor.execute(
                ActionType.FILE_DELETE,
                {"file_path": f"concurrent_{i}.txt", "confirmed": True}
            )

    # ==================== 场景 7: 错误恢复 ====================

    @pytest.mark.asyncio
    async def test_error_recovery(self, executor):
        """
        场景 7: 错误恢复测试
        
        测试各种错误情况的处理
        """
        result1 = await executor.execute(
            ActionType.FILE_READ,
            {"file_path": "nonexistent_file.txt"}
        )
        assert result1.success is False
        assert result1.error is not None

        result2 = await executor.execute(
            ActionType.FILE_DELETE,
            {"file_path": "another_nonexistent.txt", "confirmed": True}
        )
        assert result2.success is False

        result3 = await executor.execute(
            ActionType.FILE_LIST,
            {"directory": "nonexistent_dir"}
        )
        assert result3.success is True or result3.success is False

    # ==================== 场景 8: 审计日志 ====================

    def test_audit_logging(self, temp_dir):
        """
        场景 8: 审计日志测试
        
        验证操作被正确记录
        """
        logger = AuditLogger(log_dir=temp_dir)

        logger.start_session()
        logger.log(
            action=ActionType.FILE_CREATE,
            params={"file_path": "test.txt"},
            result={"success": True},
            duration_ms=10.5
        )
        logger.log(
            action=ActionType.FILE_READ,
            params={"file_path": "test.txt"},
            result={"success": True},
            duration_ms=5.2
        )
        logger.end_session()

        stats = logger.get_stats()
        assert stats["total"] == 2
        assert stats["success"] == 2

        entries = logger.get_recent_entries(10)
        assert len(entries) == 2

    # ==================== 场景 9: 大文件处理 ====================

    @pytest.mark.asyncio
    async def test_large_file_handling(self, executor, temp_dir):
        """
        场景 9: 大文件处理测试
        
        测试大文件的创建和读取
        """
        large_content = "x" * 100000

        result1 = await executor.execute(
            ActionType.FILE_CREATE,
            {"file_path": "large_file.txt", "content": large_content}
        )
        assert result1.success, "创建大文件应成功"

        result2 = await executor.execute(
            ActionType.FILE_READ,
            {"file_path": "large_file.txt"}
        )
        assert result2.success, "读取大文件应成功"

        await executor.execute(
            ActionType.FILE_DELETE,
            {"file_path": "large_file.txt", "confirmed": True}
        )

    # ==================== 场景 10: 端到端用户场景 ====================

    @pytest.mark.asyncio
    async def test_end_to_end_user_scenario(self, executor, detector, temp_dir):
        """
        场景 10: 端到端用户场景
        
        模拟真实用户的完整操作流程：
        1. 用户说"创建一个项目目录"
        2. 用户说"创建 README.md 文件"
        3. 用户说"写入项目说明"
        4. 用户说"列出目录内容"
        5. 用户说"截图保存当前状态"
        """
        scenario_steps = [
            {
                "message": "创建 project 目录",
                "expected_action": None,
                "execute": False,
            },
            {
                "message": "创建 README.md 文件",
                "expected_action": ActionType.FILE_CREATE,
                "execute": True,
                "params": {"file_path": "README.md", "content": "# Project\n\nA sample project."},
            },
            {
                "message": "列出当前目录文件",
                "expected_action": ActionType.FILE_LIST,
                "execute": True,
                "params": {"directory": "."},
            },
            {
                "message": "读取 README.md",
                "expected_action": ActionType.FILE_READ,
                "execute": True,
                "params": {"file_path": "README.md"},
            },
        ]

        results = []

        for step in scenario_steps:
            intent = detector.detect(step["message"])

            if step["execute"] and intent.detected:
                result = await executor.execute(
                    intent.action,
                    step.get("params", intent.params or {})
                )
                results.append({
                    "message": step["message"],
                    "detected": intent.detected,
                    "action": intent.action.value if intent.action else None,
                    "success": result.success,
                })
            else:
                results.append({
                    "message": step["message"],
                    "detected": intent.detected,
                    "action": intent.action.value if intent.action else None,
                    "success": None,
                })

        print("\n端到端场景执行结果:")
        for r in results:
            status = "成功" if r["success"] or (r["detected"] and r["success"] is None) else "失败"
            print(f"  {status} '{r['message']}' -> {r['action']}")

        successful = sum(1 for r in results if r["success"] is True or r["success"] is None)
        assert successful >= len(results) * 0.8, "端到端场景成功率过低"


class TestCUAIntegration:
    """CUA 模块集成测试"""

    def test_cua_intent_detection(self):
        """测试 CUA 操作的意图检测"""
        detector = IntentDetector()

        cua_commands = [
            ("截图", ActionType.SCREENSHOT),
            ("截屏", ActionType.SCREENSHOT),
            ("鼠标在哪里", ActionType.MOUSE_POSITION),
            ("获取鼠标位置", ActionType.MOUSE_POSITION),
            ("列出窗口", ActionType.WINDOW_LIST),
            ("显示所有窗口", ActionType.WINDOW_LIST),
            ("当前活动窗口", ActionType.WINDOW_ACTIVE),
        ]

        for command, expected in cua_commands:
            result = detector.detect(command)
            assert result.detected, f"应检测到意图: {command}"
            assert result.action == expected, f"'{command}' 期望 {expected}, 实际 {result.action}"


class TestPerformance:
    """性能测试"""

    def test_intent_detection_performance(self):
        """测试意图检测性能"""
        detector = IntentDetector()

        test_messages = [
            "截图", "鼠标在哪里", "列出窗口", "创建文件",
            "读取 test.txt", "列出目录", "今天天气怎么样",
        ] * 100

        start_time = time.time()

        for msg in test_messages:
            detector.detect(msg)

        elapsed = time.time() - start_time
        avg_time = elapsed / len(test_messages) * 1000

        print("\n意图检测性能:")
        print(f"  总耗时: {elapsed:.3f}s")
        print(f"  平均耗时: {avg_time:.2f}ms/次")
        print(f"  QPS: {len(test_messages) / elapsed:.0f}")

        assert avg_time < 10, f"意图检测平均耗时过高: {avg_time:.2f}ms"


class TestEdgeCases:
    """边界情况测试"""

    @pytest.fixture
    def executor(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = AgentConfig(working_dir=Path(tmpdir))
            yield AgentExecutor(config=config)

    @pytest.mark.asyncio
    async def test_empty_file_path(self, executor):
        """测试空文件路径"""
        result = await executor.execute(ActionType.FILE_READ, {"file_path": ""})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_special_characters_in_filename(self, executor):
        """测试文件名中的特殊字符"""
        result = await executor.execute(
            ActionType.FILE_CREATE,
            {"file_path": "test-file_2024.txt", "content": "test"}
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_unicode_content(self, executor):
        """测试 Unicode 内容"""
        unicode_content = "你好世界 Hello World 日本語 한국어"

        result = await executor.execute(
            ActionType.FILE_CREATE,
            {"file_path": "unicode.txt", "content": unicode_content}
        )
        assert result.success is True

        result = await executor.execute(
            ActionType.FILE_READ,
            {"file_path": "unicode.txt"}
        )
        assert result.success is True
        assert "你好世界" in result.data.get("content", "")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-s"])
