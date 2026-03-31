"""
测试生成技能 - 自动从代码生成测试用例
"""
import ast
from pathlib import Path
from typing import Any

from skills.base import SkillBase
from skills.models import SkillCategory, SkillMetadata, SkillParameter, SkillResult


class TestGeneratorSkill(SkillBase):
    """测试生成技能"""

    @classmethod
    def get_metadata(cls) -> SkillMetadata:
        return SkillMetadata(
            name="test_generator",
            display_name="Test Generator",
            description="自动生成单元测试代码",
            category=SkillCategory.UTILITY,
            version="1.0.0",
            parameters=[
                SkillParameter(
                    name="source_file",
                    type="string",
                    description="源代码文件路径",
                    required=True,
                ),
                SkillParameter(
                    name="output_dir",
                    type="string",
                    description="测试文件输出目录",
                    required=False,
                    default="tests",
                ),
                SkillParameter(
                    name="test_style",
                    type="string",
                    description="测试风格 (pytest/unittest)",
                    required=False,
                    default="pytest",
                ),
            ],
            tags=["testing", "generation", "automation"],
        )

    async def execute(self, parameters: dict[str, Any]) -> SkillResult:
        source_file = parameters.get("source_file")
        output_dir = parameters.get("output_dir", "tests")
        test_style = parameters.get("test_style", "pytest")

        if not source_file:
            return SkillResult(
                success=False,
                error="缺少 source_file 参数",
                error_code="MISSING_PARAMETER",
            )

        try:
            source_path = Path(source_file)
            if not source_path.exists():
                return SkillResult(
                    success=False,
                    error=f"文件不存在: {source_file}",
                    error_code="FILE_NOT_FOUND",
                )

            source_code = source_path.read_text(encoding="utf-8")
            tree = ast.parse(source_code)

            functions = []
            classes = []

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    if not node.name.startswith("_") or node.name.startswith("__"):
                        functions.append({
                            "name": node.name,
                            "args": [arg.arg for arg in node.args.args],
                            "returns": self._get_return_annotation(node),
                            "docstring": ast.get_docstring(node) or "",
                        })
                elif isinstance(node, ast.ClassDef):
                    methods = []
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef):
                            methods.append({
                                "name": item.name,
                                "args": [arg.arg for arg in item.args.args],
                                "returns": self._get_return_annotation(item),
                                "docstring": ast.get_docstring(item) or "",
                            })
                    classes.append({
                        "name": node.name,
                        "methods": methods,
                        "docstring": ast.get_docstring(node) or "",
                    })

            test_code = self._generate_test_code(
                source_path.stem,
                functions,
                classes,
                test_style,
            )

            output_path = Path(output_dir) / f"test_{source_path.stem}.py"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(test_code, encoding="utf-8")

            return SkillResult(
                success=True,
                data={
                    "output_file": str(output_path),
                    "functions_tested": len(functions),
                    "classes_tested": len(classes),
                    "test_style": test_style,
                },
            )

        except Exception as e:
            return SkillResult(
                success=False,
                error=str(e),
                error_code="GENERATION_ERROR",
            )

    def _get_return_annotation(self, node: ast.FunctionDef) -> str:
        """获取返回类型注解"""
        if node.returns:
            if isinstance(node.returns, ast.Name):
                return node.returns.id
            elif isinstance(node.returns, ast.Constant):
                return str(node.returns.value)
        return "Any"

    def _generate_test_code(
        self,
        module_name: str,
        functions: list[dict],
        classes: list[dict],
        test_style: str,
    ) -> str:
        """生成测试代码"""
        lines = [
            '"""',
            f'自动生成的测试文件 - {module_name}',
            '"""',
            "import pytest",
            f"from {module_name} import *",
            "",
            "",
        ]

        for func in functions:
            if func["name"].startswith("__"):
                continue

            lines.extend([
                f'class Test{func["name"].capitalize()}:',
                f'    """测试 {func["name"]} 函数"""',
                "",
                f'    def test_{func["name"]}_basic(self):',
                '        """测试基本功能"""',
                '        # TODO: 实现测试逻辑',
                '        pass',
                "",
                f'    def test_{func["name"]}_edge_cases(self):',
                '        """测试边界情况"""',
                '        # TODO: 实现边界测试',
                '        pass',
                "",
                f'    def test_{func["name"]}_error_handling(self):',
                '        """测试错误处理"""',
                '        # TODO: 实现错误处理测试',
                '        pass',
                "",
                "",
            ])

        for cls in classes:
            lines.extend([
                f'class Test{cls["name"]}:',
                f'    """测试 {cls["name"]} 类"""',
                "",
                "    @pytest.fixture",
                "    def instance(self):",
                '        """创建测试实例"""',
                '        # TODO: 创建实例',
                '        pass',
                "",
            ])

            for method in cls["methods"]:
                if method["name"].startswith("_") and not method["name"].startswith("__"):
                    continue

                lines.extend([
                    f'    def test_{method["name"]}(self, instance):',
                    f'        """测试 {method["name"]} 方法"""',
                    '        # TODO: 实现测试逻辑',
                    '        pass',
                    "",
                ])

            lines.append("")

        return "\n".join(lines)
