"""
快速验证脚本 - 复杂测试场景
"""
import os
import sys
import tempfile
import time
from pathlib import Path

server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, server_dir)

import asyncio

from agent.agent_config import ActionType
from agent.audit import AuditLogger
from agent.core import UnifiedExecutor as AgentExecutor
from agent.intent.detector import IntentDetector
from agent.security import SecurityValidator


def test_intent_detection():
    """测试意图检测"""
    print("\n" + "="*60)
    print("测试场景 1: 智能意图检测")
    print("="*60)

    detector = IntentDetector()

    test_cases = [
        ("截图", ActionType.SCREENSHOT),
        ("帮我截个图", ActionType.SCREENSHOT),
        ("鼠标在哪里", ActionType.MOUSE_POSITION),
        ("列出所有窗口", ActionType.WINDOW_LIST),
        ("创建 test.txt 文件", ActionType.FILE_CREATE),
        ("读取 config.json", ActionType.FILE_READ),
        ("列出当前目录文件", ActionType.FILE_LIST),
        ("今天天气怎么样", None),
    ]

    passed = 0
    for message, expected in test_cases:
        result = detector.detect(message)
        if expected is None:
            if not result.detected:
                print(f"  OK '{message}' -> 未检测到意图 (正确)")
                passed += 1
            else:
                print(f"  FAIL '{message}' -> 不应检测到意图，但检测到: {result.action}")
        else:
            if result.detected and result.action == expected:
                print(f"  OK '{message}' -> {result.action.value}")
                passed += 1
            else:
                print(f"  FAIL '{message}' -> 期望 {expected}, 实际 {result.action}")

    accuracy = passed / len(test_cases) * 100
    print(f"\n准确率: {passed}/{len(test_cases)} ({accuracy:.1f}%)")
    return accuracy >= 80


def test_security_validation():
    """测试安全验证"""
    print("\n" + "="*60)
    print("测试场景 2: 安全验证")
    print("="*60)

    with tempfile.TemporaryDirectory() as tmpdir:
        validator = SecurityValidator(working_dir=Path(tmpdir))

        blocked_paths = [
            "../../../etc/passwd",
            "~/.ssh/id_rsa",
            "/etc/shadow",
        ]

        passed = 0
        for path in blocked_paths:
            result = validator.validate_path(path)
            if not result.is_valid:
                print(f"  OK 阻止危险路径: {path}")
                passed += 1
            else:
                print(f"  FAIL 应阻止危险路径: {path}")

        safe_paths = ["test.txt", "subdir/file.py", "README.md"]
        for path in safe_paths:
            result = validator.validate_path(path)
            if result.is_valid:
                print(f"  OK 允许安全路径: {path}")
                passed += 1
            else:
                print(f"  FAIL 应允许安全路径: {path}")

        total = len(blocked_paths) + len(safe_paths)
        accuracy = passed / total * 100
        print(f"\n安全验证准确率: {passed}/{total} ({accuracy:.1f}%)")
        return accuracy >= 80


def test_audit_logging():
    """测试审计日志"""
    print("\n" + "="*60)
    print("测试场景 3: 审计日志")
    print("="*60)

    with tempfile.TemporaryDirectory() as tmpdir:
        logger = AuditLogger(log_dir=Path(tmpdir))

        logger.start_session()
        asyncio.run(logger.log(
            action=ActionType.FILE_CREATE,
            params={"file_path": "test.txt"},
            result={"success": True},
            duration=0.01
        ))
        asyncio.run(logger.log(
            action=ActionType.FILE_READ,
            params={"file_path": "test.txt"},
            result={"success": True},
            duration=0.005
        ))
        logger.end_session()

        stats = logger.get_stats()
        print(f"  OK 总操作数: {stats['total']}")
        print(f"  OK 成功数: {stats['success']}")

        entries = logger.get_recent_entries(10)
        print(f"  OK 日志条目: {len(entries)}")

        return stats["total"] == 2 and stats["success"] == 2


async def test_operation_chain():
    """测试操作链"""
    print("\n" + "="*60)
    print("测试场景 4: 操作链执行")
    print("="*60)

    with tempfile.TemporaryDirectory() as tmpdir:
        config = type('Config', (), {
            'working_dir': Path(tmpdir),
            'max_file_size': 10 * 1024 * 1024,
            'enable_confirm': True,
            'enable_audit': True,
            'operation_timeout': 30,
        })()

        executor = AgentExecutor(config=config)

        results = []

        result1 = await executor.execute(
            ActionType.FILE_CREATE,
            {"file_path": "test_chain.txt", "content": "Hello World"}
        )
        results.append(("创建文件", result1.success))
        print(f"  {'OK' if result1.success else 'FAIL'} 创建文件: {result1.message or result1.error}")

        result2 = await executor.execute(
            ActionType.FILE_READ,
            {"file_path": "test_chain.txt"}
        )
        results.append(("读取文件", result2.success))
        print(f"  {'OK' if result2.success else 'FAIL'} 读取文件: {result2.message or result2.error}")

        result3 = await executor.execute(
            ActionType.FILE_LIST,
            {"directory": "."}
        )
        results.append(("列出目录", result3.success))
        print(f"  {'OK' if result3.success else 'FAIL'} 列出目录: {result3.message or result3.error}")

        result4 = await executor.execute(
            ActionType.FILE_DELETE,
            {"file_path": "test_chain.txt", "confirmed": True}
        )
        results.append(("删除文件", result4.success))
        print(f"  {'OK' if result4.success else 'FAIL'} 删除文件: {result4.message or result4.error}")

        success_count = sum(1 for _, s in results if s)
        print(f"\n操作链成功率: {success_count}/{len(results)}")
        return success_count >= 3


def test_performance():
    """测试性能"""
    print("\n" + "="*60)
    print("测试场景 5: 性能测试")
    print("="*60)

    detector = IntentDetector()

    test_messages = ["截图", "鼠标在哪里", "列出窗口", "创建文件"] * 50

    start_time = time.time()
    for msg in test_messages:
        detector.detect(msg)
    elapsed = time.time() - start_time

    avg_time = elapsed / len(test_messages) * 1000
    qps = len(test_messages) / elapsed

    print(f"  总耗时: {elapsed:.3f}s")
    print(f"  平均耗时: {avg_time:.2f}ms/次")
    print(f"  QPS: {qps:.0f}")

    return avg_time < 100


def main():
    """运行所有测试"""
    print("\n" + "="*60)
    print("复杂集成测试 - AI 对话页面全功能验证")
    print("="*60)

    results = []

    results.append(("意图检测", test_intent_detection()))
    results.append(("安全验证", test_security_validation()))
    results.append(("审计日志", test_audit_logging()))
    results.append(("操作链执行", asyncio.run(test_operation_chain())))
    results.append(("性能测试", test_performance()))

    print("\n" + "="*60)
    print("测试结果汇总")
    print("="*60)

    for name, passed in results:
        status = "PASS 通过" if passed else "FAIL 失败"
        print(f"  {status} - {name}")

    passed_count = sum(1 for _, p in results if p)
    total_count = len(results)

    print(f"\n总计: {passed_count}/{total_count} 测试通过")

    return passed_count == total_count


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
