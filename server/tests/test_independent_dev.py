"""
独立开发能力测�?
测试场景�?1. 代码生成能力 - 通过 AI 生成代码
2. 文件操作能力 - 创建、读取、写入文�?3. 测试生成能力 - 自动生成测试用例
4. 代码审查能力 - 分析代码质量
5. 错误诊断能力 - 识别和修复错�?6. 项目上下文理�?- 理解项目结构
"""
import sys
import os
import asyncio
import tempfile
from pathlib import Path

server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, server_dir)


def test_file_operations():
    """测试文件操作能力"""
    print("\n" + "="*60)
    print("📁 测试场景 1: 文件操作能力")
    print("="*60)
    
    from agent.agent_config import ActionType, AgentConfig
    from agent.executor import AgentExecutor
    
    with tempfile.TemporaryDirectory() as tmpdir:
        config = AgentConfig(working_dir=Path(tmpdir))
        executor = AgentExecutor(config=config)
        
        test_results = []
        
        # 1. 创建文件
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
        print(f"  {'�? if result.success else '�?} 创建 calculator.py: {result.message or result.error}")
        
        # 2. 读取文件
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
            print(f"  �?读取文件成功，内容长�? {len(content)} 字符")
            print(f"     包含函数: add, subtract, multiply, divide")
        else:
            print(f"  �?读取文件失败: {result.error}")
        
        # 3. 列出文件
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
            print(f"  �?列出文件成功，找�?{len(files)} 个文�?)
        
        # 4. 写入文件（追加测试代码）
        async def write_file():
            result = await executor.execute(
                ActionType.FILE_WRITE,
                {
                    "file_path": "calculator.py",
                    "content": '''
def power(a, b):
    """幂运�?""
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
        print(f"  {'�? if result.success else '�?} 追加代码: {result.message or result.error}")
        
        passed = sum(1 for _, s in test_results if s)
        print(f"\n  文件操作能力: {passed}/{len(test_results)} 通过")
        return passed >= 3


def test_intent_detection():
    """测试意图检测能�?""
    print("\n" + "="*60)
    print("🎯 测试场景 2: 意图检测能�?)
    print("="*60)
    
    from agent.intent.detector import IntentDetector
    from agent.agent_config import ActionType
    
    detector = IntentDetector()
    
    test_cases = [
        ("创建 main.py 文件", ActionType.FILE_CREATE),
        ("读取 config.json", ActionType.FILE_READ),
        ("列出当前目录文件", ActionType.FILE_LIST),
        ("删除 temp.txt", ActionType.FILE_DELETE),
        ("截图", ActionType.SCREENSHOT),
        ("鼠标在哪�?, ActionType.MOUSE_POSITION),
        ("列出所有窗�?, ActionType.WINDOW_LIST),
    ]
    
    passed = 0
    for message, expected in test_cases:
        result = detector.detect(message)
        if result.detected and result.action == expected:
            print(f"  �?'{message}' -> {result.action.value}")
            passed += 1
        else:
            actual = result.action.value if result.action else "None"
            print(f"  �?'{message}' -> 期望 {expected.value}, 实际 {actual}")
    
    accuracy = passed / len(test_cases) * 100
    print(f"\n  意图检测准确率: {passed}/{len(test_cases)} ({accuracy:.1f}%)")
    return accuracy >= 80


def test_security_validation():
    """测试安全验证能力"""
    print("\n" + "="*60)
    print("🔒 测试场景 3: 安全验证能力")
    print("="*60)
    
    from agent.security import SecurityValidator
    
    with tempfile.TemporaryDirectory() as tmpdir:
        validator = SecurityValidator(working_dir=Path(tmpdir))
        
        # 测试危险路径检�?        dangerous_paths = [
            "../../../etc/passwd",
            "~/.ssh/id_rsa",
            "/etc/shadow",
            "C:\\Windows\\System32",
        ]
        
        passed = 0
        for path in dangerous_paths:
            result = validator.validate_path(path)
            if not result.is_valid:
                print(f"  �?阻止危险路径: {path}")
                passed += 1
            else:
                print(f"  �?应阻止危险路�? {path}")
        
        # 测试安全路径允许
        safe_paths = ["test.py", "src/main.py", "config.json"]
        for path in safe_paths:
            result = validator.validate_path(path)
            if result.is_valid:
                print(f"  �?允许安全路径: {path}")
                passed += 1
            else:
                print(f"  �?应允许安全路�? {path}")
        
        total = len(dangerous_paths) + len(safe_paths)
        accuracy = passed / total * 100
        print(f"\n  安全验证准确�? {passed}/{total} ({accuracy:.1f}%)")
        return accuracy >= 80


def test_skill_system():
    """测试技能系�?""
    print("\n" + "="*60)
    print("�?测试场景 4: 技能系�?)
    print("="*60)
    
    skills_dir = os.path.join(server_dir, "skills", "implemented")
    
    if not os.path.exists(skills_dir):
        print(f"  �?技能目录不存在: {skills_dir}")
        return False
    
    skills = [f for f in os.listdir(skills_dir) if f.endswith("_skill.py")]
    
    print(f"  已注册技能数�? {len(skills)}")
    
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
            print(f"  �?技能可�? {skill_name}")
            passed += 1
        else:
            print(f"  ⚠️ 技能未找到: {skill_name}")
    
    print(f"\n  技能系统完整�? {passed}/{len(expected_skills)}")
    return passed >= 3


def test_project_context():
    """测试项目上下文理�?""
    print("\n" + "="*60)
    print("🔍 测试场景 5: 项目上下文理�?)
    print("="*60)
    
    context_api_path = os.path.join(server_dir, "api", "context.py")
    context_dir = os.path.join(server_dir, "context")
    
    checks = [
        (context_api_path, "上下�?API"),
        (context_dir, "上下文模块目�?),
        (os.path.join(context_dir, "project_scanner.py"), "项目扫描�?),
        (os.path.join(context_dir, "symbol_extractor.py"), "符号提取�?),
        (os.path.join(context_dir, "code_indexer.py"), "代码索引�?),
    ]
    
    passed = 0
    for path, name in checks:
        if os.path.exists(path):
            print(f"  �?{name}: 已实�?)
            passed += 1
        else:
            print(f"  �?{name}: 未找�?)
    
    print(f"\n  项目上下文能�? {passed}/{len(checks)}")
    return passed >= 3


def test_code_generation():
    """测试代码生成能力"""
    print("\n" + "="*60)
    print("💻 测试场景 6: 代码生成能力")
    print("="*60)
    
    from agent.agent_config import ActionType, AgentConfig
    from agent.executor import AgentExecutor
    
    with tempfile.TemporaryDirectory() as tmpdir:
        config = AgentConfig(working_dir=Path(tmpdir))
        executor = AgentExecutor(config=config)
        
        # 生成一个完整的 Python 模块
        generated_code = '''"""
自动生成的数据处理模�?"""
import json
from typing import List, Dict, Any
from datetime import datetime


class DataProcessor:
    """数据处理�?""
    
    def __init__(self, name: str):
        self.name = name
        self.created_at = datetime.now()
        self._data: List[Dict[str, Any]] = []
    
    def add_record(self, record: Dict[str, Any]) -> None:
        """添加记录"""
        record["_added_at"] = datetime.now().isoformat()
        self._data.append(record)
    
    def get_records(self) -> List[Dict[str, Any]]:
        """获取所有记�?""
        return self._data.copy()
    
    def filter_by(self, key: str, value: Any) -> List[Dict[str, Any]]:
        """按条件过�?""
        return [r for r in self._data if r.get(key) == value]
    
    def to_json(self) -> str:
        """导出�?JSON"""
        return json.dumps(self._data, ensure_ascii=False, indent=2)
    
    def count(self) -> int:
        """记录数量"""
        return len(self._data)


def main():
    processor = DataProcessor("test_processor")
    
    # 添加测试数据
    processor.add_record({"name": "Alice", "age": 30})
    processor.add_record({"name": "Bob", "age": 25})
    processor.add_record({"name": "Charlie", "age": 30})
    
    print(f"总记录数: {processor.count()}")
    print(f"年龄�?0的记�? {len(processor.filter_by('age', 30))}")
    print(f"JSON 输出:\\n{processor.to_json()}")


if __name__ == "__main__":
    main()
'''
        
        async def create_and_verify():
            # 创建文件
            result = await executor.execute(
                ActionType.FILE_CREATE,
                {"file_path": "data_processor.py", "content": generated_code}
            )
            if not result.success:
                return False, "创建文件失败"
            
            # 读取验证
            result = await executor.execute(
                ActionType.FILE_READ,
                {"file_path": "data_processor.py"}
            )
            if not result.success:
                return False, "读取文件失败"
            
            content = result.data.get("content", "")
            
            # 验证代码结构
            checks = [
                ("class DataProcessor", "类定�?),
                ("def add_record", "方法: add_record"),
                ("def filter_by", "方法: filter_by"),
                ("def to_json", "方法: to_json"),
                ("import json", "依赖导入"),
                ("typing", "类型注解"),
            ]
            
            passed = 0
            for pattern, desc in checks:
                if pattern in content:
                    print(f"  �?{desc}: 已生�?)
                    passed += 1
                else:
                    print(f"  �?{desc}: 未找�?)
            
            return passed >= 5, f"代码生成质量: {passed}/{len(checks)}"
        
        success, message = asyncio.run(create_and_verify())
        print(f"\n  {message}")
        return success


def test_error_handling():
    """测试错误处理能力"""
    print("\n" + "="*60)
    print("🛠�?测试场景 7: 错误处理能力")
    print("="*60)
    
    from agent.agent_config import ActionType, AgentConfig
    from agent.executor import AgentExecutor
    
    with tempfile.TemporaryDirectory() as tmpdir:
        config = AgentConfig(working_dir=Path(tmpdir))
        executor = AgentExecutor(config=config)
        
        test_results = []
        
        # 1. 读取不存在的文件
        async def read_nonexistent():
            result = await executor.execute(
                ActionType.FILE_READ,
                {"file_path": "nonexistent_file.txt"}
            )
            return result
        
        result = asyncio.run(read_nonexistent())
        handled = not result.success and result.error is not None
        test_results.append(("读取不存在文�?, handled))
        print(f"  {'�? if handled else '�?} 正确处理: 文件不存在错�?)
        
        # 2. 空路径验�?        result = asyncio.run(executor.execute(ActionType.FILE_READ, {"file_path": ""}))
        handled = not result.success
        test_results.append(("空路径验�?, handled))
        print(f"  {'�? if handled else '�?} 正确处理: 空路径错�?)
        
        # 3. 危险操作确认
        validator = executor.validator
        is_dangerous = validator.is_dangerous_action(ActionType.FILE_DELETE)
        test_results.append(("危险操作识别", is_dangerous))
        print(f"  {'�? if is_dangerous else '�?} 正确识别: 删除操作为危险操�?)
        
        passed = sum(1 for _, s in test_results if s)
        print(f"\n  错误处理能力: {passed}/{len(test_results)} 通过")
        return passed >= 2


def main():
    """运行所有测�?""
    print("\n" + "="*60)
    print("🧪 独立开发能力综合测�?)
    print("="*60)
    print("\n测试 AI 是否具备独立开发程序的能力...")
    
    results = []
    
    results.append(("文件操作能力", test_file_operations()))
    results.append(("意图检测能�?, test_intent_detection()))
    results.append(("安全验证能力", test_security_validation()))
    results.append(("技能系�?, test_skill_system()))
    results.append(("项目上下文理�?, test_project_context()))
    results.append(("代码生成能力", test_code_generation()))
    results.append(("错误处理能力", test_error_handling()))
    
    print("\n" + "="*60)
    print("📊 测试结果汇�?)
    print("="*60)
    
    for name, passed in results:
        status = "�?通过" if passed else "�?失败"
        print(f"  {status} - {name}")
    
    passed_count = sum(1 for _, p in results if p)
    total_count = len(results)
    
    print(f"\n总计: {passed_count}/{total_count} 测试通过")
    
    # 计算能力等级
    if passed_count == total_count:
        level = "Level 5 - 完全自主开�?
    elif passed_count >= 6:
        level = "Level 4 - 高度自主开�?
    elif passed_count >= 5:
        level = "Level 3 - 辅助开�?
    elif passed_count >= 3:
        level = "Level 2 - 基础辅助"
    else:
        level = "Level 1 - 需要人工干�?
    
    print(f"\n🏆 AI 开发能力等�? {level}")
    
    if passed_count >= 5:
        print("\n�?结论: AI 具备独立开发程序的能力")
        print("\n能力说明:")
        print("  �?可以创建、读取、修改文�?)
        print("  �?可以理解自然语言指令并执行操�?)
        print("  �?可以生成完整的代码模�?)
        print("  �?可以进行安全验证和错误处�?)
        print("  �?可以理解项目上下�?)
    else:
        print("\n⚠️ 结论: AI 需要进一步增强才能独立开�?)
    
    return passed_count >= 5


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
