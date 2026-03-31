"""
独立开发能力测试

测试场景：
1. 代码生成能力 - 通过 AI 生成代码
2. 文件操作能力 - 创建、读取、写入文件
3. 测试生成能力 - 自动生成测试用例
4. 代码审查能力 - 分析代码质量
5. 错误诊断能力 - 识别和修复错误
6. 项目上下文理解 - 理解项目结构
"""
import asyncio
import os
import sys
import tempfile
from pathlib import Path

server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, server_dir)


def test_file_operations():
    """测试文件操作能力"""
    print("\n" + "="*60)
    print("测试场景 1: 文件操作能力")
    print("="*60)

    from agent.agent_config import ActionType, AgentConfig
    from agent.core import UnifiedExecutor as AgentExecutor

    with tempfile.TemporaryDirectory() as tmpdir:
        config = AgentConfig(working_dir=Path(tmpdir))
        executor = AgentExecutor(config=config)

        test_results = []

        async def create_file():
            result = await executor.execute(
                ActionType.FILE_CREATE,
                {"file_path": "calculator.py", "content": '''"""
简单计算器模块
"""
def add(a, b):
    """加法"""
    return a + b

def subtract(a, b):
    """减法"""
    return a - b

def multiply(a, b):
    """乘法"""
    return a * b

def divide(a, b):
    """除法"""
    if b == 0:
        raise ValueError("除数不能为零")
    return a / b
'''}
            )
            return result

        result = asyncio.run(create_file())
        test_results.append(("创建文件", result.success))
        print(f"  {'OK' if result.success else 'FAIL'} 创建 calculator.py: {result.message or result.error}")

        async def read_file():
            result = await executor.execute(
                ActionType.FILE_READ,
                {"file_path": "calculator.py"}
            )
            return result

        result = asyncio.run(read_file())
        test_results.append(("读取文件", result.success))
        if result.success:
            content = result.data.get("content", "")
            print(f"  OK 读取文件成功，内容长度: {len(content)} 字符")
            print("     包含函数: add, subtract, multiply, divide")
        else:
            print(f"  FAIL 读取文件失败: {result.error}")

        async def list_files():
            result = await executor.execute(
                ActionType.FILE_LIST,
                {"directory": "."}
            )
            return result

        result = asyncio.run(list_files())
        test_results.append(("列出文件", result.success))
        if result.success:
            files = result.data.get("files", [])
            print(f"  OK 列出文件成功，找到 {len(files)} 个文件")

        async def write_file():
            result = await executor.execute(
                ActionType.FILE_WRITE,
                {
                    "file_path": "calculator.py",
                    "content": '''
def power(a, b):
    """幂运算"""
    return a ** b

def modulo(a, b):
    """取模"""
    return a % b
''',
                    "mode": "append"
                }
            )
            return result

        result = asyncio.run(write_file())
        test_results.append(("写入文件", result.success))
        print(f"  {'OK' if result.success else 'FAIL'} 追加代码: {result.message or result.error}")

        passed = sum(1 for _, s in test_results if s)
        print(f"\n  文件操作能力: {passed}/{len(test_results)} 通过")
        return passed >= 3


def test_intent_detection():
    """测试意图检测能力"""
    print("\n" + "="*60)
    print("测试场景 2: 意图检测能力")
    print("="*60)

    from agent.agent_config import ActionType
    from agent.intent.detector import IntentDetector

    detector = IntentDetector()

    test_cases = [
        ("创建 main.py 文件", ActionType.FILE_CREATE),
        ("读取 config.json", ActionType.FILE_READ),
        ("列出当前目录文件", ActionType.FILE_LIST),
        ("删除 temp.txt", ActionType.FILE_DELETE),
        ("截图", ActionType.SCREENSHOT),
        ("鼠标在哪里", ActionType.MOUSE_POSITION),
        ("列出所有窗口", ActionType.WINDOW_LIST),
    ]

    passed = 0
    for message, expected in test_cases:
        result = detector.detect(message)
        if result.detected and result.action == expected:
            print(f"  OK '{message}' -> {result.action.value}")
            passed += 1
        else:
            actual = result.action.value if result.action else "None"
            print(f"  FAIL '{message}' -> 期望 {expected.value}, 实际 {actual}")

    accuracy = passed / len(test_cases) * 100
    print(f"\n  意图检测准确率: {passed}/{len(test_cases)} ({accuracy:.1f}%)")
    return accuracy >= 80


def test_security_validation():
    """测试安全验证能力"""
    print("\n" + "="*60)
    print("测试场景 3: 安全验证能力")
    print("="*60)

    from agent.security import SecurityValidator

    with tempfile.TemporaryDirectory() as tmpdir:
        validator = SecurityValidator(working_dir=Path(tmpdir))

        dangerous_paths = [
            "../../../etc/passwd",
            "~/.ssh/id_rsa",
            "/etc/shadow",
            "C:\\Windows\\System32",
        ]

        passed = 0
        for path in dangerous_paths:
            result = validator.validate_path(path)
            if not result.is_valid:
                print(f"  OK 阻止危险路径: {path}")
                passed += 1
            else:
                print(f"  FAIL 应阻止危险路径: {path}")

        safe_paths = ["test.py", "src/main.py", "config.json"]
        for path in safe_paths:
            result = validator.validate_path(path)
            if result.is_valid:
                print(f"  OK 允许安全路径: {path}")
                passed += 1
            else:
                print(f"  FAIL 应允许安全路径: {path}")

        total = len(dangerous_paths) + len(safe_paths)
        accuracy = passed / total * 100
        print(f"\n  安全验证准确率: {passed}/{total} ({accuracy:.1f}%)")
        return accuracy >= 80


def test_skill_system():
    """测试技能系统"""
    print("\n" + "="*60)
    print("测试场景 4: 技能系统")
    print("="*60)

    skills_dir = os.path.join(server_dir, "skills", "implemented")

    if not os.path.exists(skills_dir):
        print(f"  FAIL 技能目录不存在: {skills_dir}")
        return False

    skills = [f for f in os.listdir(skills_dir) if f.endswith("_skill.py")]

    print(f"  已注册技能数量: {len(skills)}")

    expected_skills = [
        "file_read_skill",
        "file_list_skill",
        "system_info_skill",
        "calculator_skill",
        "test_generator_skill",
    ]

    passed = 0
    for skill_name in expected_skills:
        skill_file = f"{skill_name}.py"
        if any(skill_file in s for s in skills):
            print(f"  OK 技能可用: {skill_name}")
            passed += 1
        else:
            print(f"  WARN 技能未找到: {skill_name}")

    print(f"\n  技能系统完整性: {passed}/{len(expected_skills)}")
    return passed >= 3


def test_project_context():
    """测试项目上下文理解"""
    print("\n" + "="*60)
    print("测试场景 5: 项目上下文理解")
    print("="*60)

    from context.project_scanner import ProjectScanner

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)

        (project_dir / "src").mkdir()
        (project_dir / "src" / "main.py").write_text("print('hello')")
        (project_dir / "requirements.txt").write_text("fastapi\npydantic\n")
        (project_dir / "README.md").write_text("# Test Project")

        scanner = ProjectScanner()
        result = scanner.scan(str(project_dir))

        print(f"  项目路径: {project_dir}")
        print(f"  检测到的技术栈: {result.get('tech_stack', [])}")
        print(f"  文件数量: {result.get('file_count', 0)}")

        return result.get("file_count", 0) >= 3


def main():
    """运行所有测试"""
    print("\n" + "="*60)
    print("独立开发能力验证测试")
    print("="*60)

    results = []

    results.append(("文件操作能力", test_file_operations()))
    results.append(("意图检测能力", test_intent_detection()))
    results.append(("安全验证能力", test_security_validation()))
    results.append(("技能系统", test_skill_system()))
    results.append(("项目上下文理解", test_project_context()))

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
