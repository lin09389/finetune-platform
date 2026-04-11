"""
????????
?????????????????????????????????
"""
import asyncio
import os
import sys
import tempfile
from pathlib import Path

server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, server_dir)


def test_file_operations():
    """????????"""
    from agent.agent_config import ActionType, AgentConfig
    from agent.core import UnifiedExecutor as AgentExecutor

    with tempfile.TemporaryDirectory() as tmpdir:
        config = AgentConfig(working_dir=Path(tmpdir))
        executor = AgentExecutor(config=config)

        async def create_file():
            return await executor.execute(
                ActionType.FILE_CREATE,
                {
                    "file_path": "calculator.py",
                    "content": "def add(a, b):\n    return a + b\n",
                },
            )

        async def read_file():
            return await executor.execute(ActionType.FILE_READ, {"file_path": "calculator.py"})

        async def list_files():
            return await executor.execute(ActionType.FILE_LIST, {"directory": "."})

        async def write_file():
            return await executor.execute(
                ActionType.FILE_WRITE,
                {
                    "file_path": "calculator.py",
                    "content": "\ndef power(a, b):\n    return a ** b\n",
                    "mode": "append",
                },
            )

        create_result = asyncio.run(create_file())
        assert create_result.success

        read_result = asyncio.run(read_file())
        assert read_result.success
        assert "add" in read_result.data.get("content", "")

        list_result = asyncio.run(list_files())
        assert list_result.success

        write_result = asyncio.run(write_file())
        assert write_result.success


def test_intent_detection():
    """????????"""
    from agent.intent.detector import IntentDetector

    detector = IntentDetector()
    test_cases = [
        "create main.py",
        "read config.json",
        "list files",
        "delete temp.txt",
        "screenshot",
        "hello",
        "what's the weather like today",
    ]

    detected = 0
    for message in test_cases:
        result = detector.detect(message)
        assert hasattr(result, "detected")
        assert hasattr(result, "action")
        if result.detected:
            detected += 1

    assert detected >= 1


def test_security_validation():
    """????????"""
    from agent.security import SecurityValidator

    with tempfile.TemporaryDirectory() as tmpdir:
        validator = SecurityValidator(working_dir=Path(tmpdir))

        dangerous_paths = [
            "../../../etc/passwd",
            "~/.ssh/id_rsa",
            "/etc/shadow",
            r"C:\Windows\System32",
        ]
        for path in dangerous_paths:
            assert not validator.validate_path(path).is_valid

        safe_paths = ["test.py", "src/main.py", "config.json"]
        for path in safe_paths:
            assert validator.validate_path(path).is_valid


def test_skill_system():
    """??????"""
    skills_dir = os.path.join(server_dir, "skills", "implemented")
    assert os.path.exists(skills_dir)

    skills = [f for f in os.listdir(skills_dir) if f.endswith("_skill.py")]
    expected_skills = [
        "file_read_skill",
        "file_list_skill",
        "system_info_skill",
        "calculator_skill",
        "test_generator_skill",
    ]

    passed = sum(1 for skill_name in expected_skills if f"{skill_name}.py" in skills)
    assert passed >= 3


def test_project_context():
    """?????????"""
    from context.project_scanner import ProjectScanner

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        (project_dir / "src").mkdir()
        (project_dir / "src" / "main.py").write_text("print('hello')", encoding="utf-8")
        (project_dir / "requirements.txt").write_text("fastapi\npydantic\n", encoding="utf-8")
        (project_dir / "README.md").write_text("# Test Project", encoding="utf-8")

        scanner = ProjectScanner()
        result = scanner.scan(str(project_dir))

        assert result.get("file_count", 0) >= 1
        tech_stack = [item.lower() for item in result.get("tech_stack", [])]
        assert "python" in tech_stack
        assert "fastapi" in tech_stack
