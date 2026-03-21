"""
MD Skill 加载器：将 Markdown 格式的 skill 文件转换为可执行的 Python skill
"""
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from skills.base import SkillBase
from skills.models import (
    SkillCategory,
    SkillMetadata,
    SkillParameter,
    SkillParameterType,
    SkillResult,
)


class MDSkillLoader:
    """加载 MD 格式的 skill 文件"""
    
    def __init__(self, skills_dir: Optional[Path] = None):
        # 默认从项目的 skills/md_skills 目录加载
        self.skills_dir = skills_dir or Path(__file__).parent / "md_skills"
    
    def load_all(self) -> List[type]:
        """加载所有 MD skill 文件"""
        skills = []
        
        if not self.skills_dir.exists():
            return skills
        
        for skill_dir in self.skills_dir.iterdir():
            if skill_dir.is_dir():
                skill_file = skill_dir / "SKILL.md"
                if skill_file.exists():
                    skill_class = self.load(skill_file)
                    if skill_class:
                        skills.append(skill_class)
        
        return skills
    
    def load(self, md_file: Path) -> Optional[type]:
        """加载单个 MD skill 文件"""
        try:
            content = md_file.read_text(encoding="utf-8")
            frontmatter, body = self._parse_frontmatter(content)
            
            if not frontmatter:
                return None
            
            name = frontmatter.get("name", md_file.parent.name)
            description = frontmatter.get("description", "")
            
            return self._create_skill_class(name, description, body)
        
        except Exception as e:
            print(f"加载 MD skill 失败: {md_file}: {e}")
            return None
    
    def _parse_frontmatter(self, content: str) -> tuple:
        """解析 YAML frontmatter"""
        pattern = r"^---\s*\n(.*?)\n---\s*\n(.*)$"
        match = re.match(pattern, content, re.DOTALL)
        
        if not match:
            return None, content
        
        frontmatter_str, body = match.groups()
        frontmatter = {}
        
        for line in frontmatter_str.split("\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                frontmatter[key.strip()] = value.strip().strip('"\'')
        
        return frontmatter, body
    
    def _create_skill_class(self, name: str, description: str, body: str) -> type:
        """动态创建 skill 类"""
        
        class MDSkill(SkillBase):
            _md_name = name
            _md_description = description
            _md_content = body
            
            @classmethod
            def get_metadata(cls) -> SkillMetadata:
                return SkillMetadata(
                    name=cls._md_name,
                    display_name=cls._md_name.replace("-", " ").replace("_", " ").title(),
                    description=cls._md_description,
                    version="1.0.0",
                    category=SkillCategory.CUSTOM,
                    tags=["md-skill", "dynamic"],
                    parameters=[
                        SkillParameter(
                            name="query",
                            type=SkillParameterType.STRING,
                            description="用户查询",
                            required=True,
                        ),
                    ],
                    examples=[{"query": "示例查询"}],
                )
            
            async def execute(self, **kwargs) -> SkillResult:
                query = kwargs.get("query", "")
                
                return SkillResult(
                    success=True,
                    data={
                        "skill_name": self._md_name,
                        "description": self._md_description,
                        "instructions": self._md_content,
                        "query": query,
                        "message": f"已加载 skill: {self._md_name}，请根据以下指令处理用户请求",
                    },
                )
        
        MDSkill.__name__ = f"{name.replace('-', '_').title()}Skill"
        return MDSkill


def load_md_skills(registry):
    """加载所有 MD skills 到注册表"""
    loader = MDSkillLoader()
    for skill_class in loader.load_all():
        registry.register(skill_class)
    return loader.load_all()
