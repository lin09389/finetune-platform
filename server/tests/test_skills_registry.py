"""
技能模块单元测试
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from skills.base import SkillBase
from skills.models import (
    SkillCategory,
    SkillMetadata,
    SkillParameter,
    SkillResult,
)
from skills.registry import SkillRegistry, get_registry, register_skill


class MockSkill(SkillBase):
    """测试用模拟技能"""

    @classmethod
    def get_metadata(cls) -> SkillMetadata:
        return SkillMetadata(
            name="mock_skill",
            display_name="Mock Skill",
            description="A mock skill for testing",
            category=SkillCategory.UTILITY,
            version="1.0.0",
            parameters=[
                SkillParameter(
                    name="input",
                    type="string",
                    description="Input text",
                    required=True
                )
            ],
            tags=["test", "mock"],
        )

    async def execute(self, parameters: dict) -> SkillResult:
        input_text = parameters.get("input", "")
        return SkillResult(
            success=True,
            data={"output": f"Processed: {input_text}"},
        )


class FailingSkill(SkillBase):
    """测试用失败技能"""

    @classmethod
    def get_metadata(cls) -> SkillMetadata:
        return SkillMetadata(
            name="failing_skill",
            display_name="Failing Skill",
            description="A skill that always fails",
            category=SkillCategory.UTILITY,
            version="1.0.0",
        )

    async def execute(self, parameters: dict) -> SkillResult:
        return SkillResult(
            success=False,
            error="Intentional failure",
            error_code="TEST_FAILURE",
        )


class TestSkillModels:
    """技能模型测试"""

    def test_skill_metadata(self):
        """测试技能元数据"""
        metadata = SkillMetadata(
            name="test_skill",
            display_name="Test Skill",
            description="Test description",
            category=SkillCategory.UTILITY,
            version="1.0.0",
        )
        assert metadata.name == "test_skill"
        assert metadata.category == SkillCategory.UTILITY

    def test_skill_parameter(self):
        """测试技能参数"""
        param = SkillParameter(
            name="test_param",
            type="string",
            description="Test parameter",
            required=True,
            default="default_value"
        )
        assert param.name == "test_param"
        assert param.required is True
        assert param.default == "default_value"

    def test_skill_result_success(self):
        """测试成功结果"""
        result = SkillResult(
            success=True,
            data={"key": "value"}
        )
        assert result.success is True
        assert result.data["key"] == "value"

    def test_skill_result_failure(self):
        """测试失败结果"""
        result = SkillResult(
            success=False,
            error="Something went wrong",
            error_code="ERROR_CODE"
        )
        assert result.success is False
        assert result.error == "Something went wrong"


class TestSkillBase:
    """技能基类测试"""

    def test_get_metadata(self):
        """测试获取元数据"""
        metadata = MockSkill.get_metadata()
        assert metadata.name == "mock_skill"
        assert metadata.category == SkillCategory.UTILITY


class TestSkillRegistry:
    """技能注册表测试"""

    @pytest.fixture
    def registry(self):
        registry = SkillRegistry.get_instance()
        registry._skills = {}
        registry._instances = {}
        registry._executions = {}
        return registry

    def test_singleton(self, registry):
        """测试单例模式"""
        registry1 = SkillRegistry.get_instance()
        registry2 = SkillRegistry.get_instance()
        assert registry1 is registry2

    def test_register_skill(self, registry):
        """测试注册技能"""
        result = registry.register(MockSkill)
        assert result is True
        assert registry.has_skill("mock_skill")

    def test_register_duplicate(self, registry):
        """测试重复注册"""
        registry.register(MockSkill)
        result = registry.register(MockSkill)
        assert result is False

    def test_unregister_skill(self, registry):
        """测试注销技能"""
        registry.register(MockSkill)
        result = registry.unregister("mock_skill")
        assert result is True
        assert not registry.has_skill("mock_skill")

    def test_unregister_nonexistent(self, registry):
        """测试注销不存在的技能"""
        result = registry.unregister("nonexistent")
        assert result is False

    def test_get_skill(self, registry):
        """测试获取技能"""
        registry.register(MockSkill)
        skill = registry.get_skill("mock_skill")
        assert skill is not None
        assert isinstance(skill, MockSkill)

    def test_get_skill_nonexistent(self, registry):
        """测试获取不存在的技能"""
        skill = registry.get_skill("nonexistent")
        assert skill is None

    def test_get_metadata(self, registry):
        """测试获取元数据"""
        registry.register(MockSkill)
        metadata = registry.get_metadata("mock_skill")
        assert metadata is not None
        assert metadata.name == "mock_skill"

    def test_list_skills(self, registry):
        """测试列出技能"""
        registry.register(MockSkill)
        registry.register(FailingSkill)

        skills = registry.list_skills()
        assert "mock_skill" in skills
        assert "failing_skill" in skills

    def test_list_skills_by_category(self, registry):
        """测试按类别列出技能"""
        registry.register(MockSkill)

        skills = registry.list_skills_by_category(SkillCategory.UTILITY)
        assert "mock_skill" in skills

    def test_list_skills_by_tag(self, registry):
        """测试按标签列出技能"""
        registry.register(MockSkill)

        skills = registry.list_skills_by_tag("test")
        assert "mock_skill" in skills

    def test_get_all_metadata(self, registry):
        """测试获取所有元数据"""
        registry.register(MockSkill)

        all_metadata = registry.get_all_metadata()
        assert "mock_skill" in all_metadata

    def test_get_stats(self, registry):
        """测试获取统计信息"""
        registry.register(MockSkill)

        stats = registry.get_stats()
        assert stats["total_skills"] >= 1
        assert "categories" in stats


class TestRegisterDecorator:
    """注册装饰器测试"""

    def test_register_decorator(self):
        """测试装饰器注册"""
        @register_skill
        class DecoratedSkill(SkillBase):
            @classmethod
            def get_metadata(cls) -> SkillMetadata:
                return SkillMetadata(
                    name="decorated_skill",
                    display_name="Decorated Skill",
                    description="Decorated skill",
                    category=SkillCategory.UTILITY,
                    version="1.0.0",
                )

            async def execute(self, parameters: dict) -> SkillResult:
                return SkillResult(success=True)

        registry = get_registry()
        assert registry.has_skill("decorated_skill")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
