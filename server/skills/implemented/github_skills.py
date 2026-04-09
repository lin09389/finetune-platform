"""
GitHub 项目分析技能
分析 GitHub 仓库，学习代码模式，提供改进建议
"""
import json
import re
from datetime import datetime

from skills.base import SkillBase
from skills.models import (
    SkillCategory,
    SkillMetadata,
    SkillParameter,
    SkillParameterType,
    SkillResult,
)


class GitHubAnalyzerSkill(SkillBase):
    """分析 GitHub 仓库"""

    @classmethod
    def get_metadata(cls) -> SkillMetadata:
        return SkillMetadata(
            name="github_analyzer",
            display_name="GitHub 项目分析",
            description="分析 GitHub 仓库，学习代码模式，提供改进建议",
            version="1.0.0",
            category=SkillCategory.ANALYSIS,
            tags=["github", "analysis", "code-review", "best-practices"],
            parameters=[
                SkillParameter(
                    name="repo_url",
                    type=SkillParameterType.STRING,
                    description="GitHub 仓库 URL (例如: https://github.com/owner/repo)",
                    required=True,
                ),
                SkillParameter(
                    name="focus_area",
                    type=SkillParameterType.STRING,
                    description="分析重点: architecture, security, performance, all",
                    required=False,
                    default="all",
                ),
            ],
            examples=[
                {"repo_url": "https://github.com/modelscope/swift", "focus_area": "architecture"},
                {"repo_url": "https://github.com/facebook/react"},
            ],
        )

    async def execute(self, **kwargs) -> SkillResult:
        repo_url = kwargs.get("repo_url", "")
        focus_area = kwargs.get("focus_area", "all")

        if not repo_url:
            return SkillResult(
                success=False,
                error="请提供 GitHub 仓库 URL",
                error_code="MISSING_REPO_URL",
            )

        try:
            owner, repo = self._parse_github_url(repo_url)
            if not owner or not repo:
                return SkillResult(
                    success=False,
                    error="无效的 GitHub URL 格式",
                    error_code="INVALID_GITHUB_URL",
                )

            repo_info = await self._fetch_repo_info(owner, repo)
            readme_content = await self._fetch_readme(owner, repo)
            structure = await self._fetch_structure(owner, repo)

            analysis = {
                "repository": {
                    "name": repo_info.get("name", repo),
                    "full_name": f"{owner}/{repo}",
                    "description": repo_info.get("description", ""),
                    "stars": repo_info.get("stargazers_count", 0),
                    "language": repo_info.get("language", "Unknown"),
                    "topics": repo_info.get("topics", []),
                    "license": repo_info.get("license", {}).get("spdx_id", "No license") if repo_info.get("license") else "No license",
                },
                "analysis": {
                    "focus_area": focus_area,
                    "structure": structure,
                    "readme_summary": self._summarize_readme(readme_content),
                    "recommendations": self._generate_recommendations(repo_info, structure, focus_area),
                },
                "analyzed_at": datetime.now().isoformat(),
            }

            return SkillResult(
                success=True,
                data=analysis,
            )

        except Exception as e:
            return SkillResult(
                success=False,
                error=f"分析失败: {str(e)}",
                error_code="ANALYSIS_ERROR",
            )

    def _parse_github_url(self, url: str) -> tuple:
        patterns = [
            r"github\.com/([^/]+)/([^/]+)/?",
            r"github\.com/([^/]+)/([^/]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1), match.group(2)
        return None, None

    async def _fetch_repo_info(self, owner: str, repo: str) -> dict:
        import urllib.request

        url = f"https://api.github.com/repos/{owner}/{repo}"
        headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "FinetunePlatform/1.0"}

        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as response:
                return json.loads(response.read().decode())
        except Exception:
            return {"name": repo, "full_name": f"{owner}/{repo}"}

    async def _fetch_readme(self, owner: str, repo: str) -> str:
        import urllib.request

        url = f"https://api.github.com/repos/{owner}/{repo}/readme"
        headers = {"Accept": "application/vnd.github.v3.raw", "User-Agent": "FinetunePlatform/1.0"}

        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.read().decode()
        except Exception:
            return ""

    async def _fetch_structure(self, owner: str, repo: str) -> list[dict]:
        import urllib.request

        url = f"https://api.github.com/repos/{owner}/{repo}/contents/"
        headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "FinetunePlatform/1.0"}

        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as response:
                contents = json.loads(response.read().decode())
                return [{"name": item["name"], "type": item["type"]} for item in contents]
        except Exception:
            return []

    def _summarize_readme(self, readme: str) -> str:
        if not readme:
            return "无 README 文件"

        lines = readme.split("\n")[:10]
        summary = "\n".join(line for line in lines if line.strip())
        return summary[:500] + "..." if len(summary) > 500 else summary

    def _generate_recommendations(self, repo_info: dict, structure: list[dict], focus_area: str) -> list[dict]:
        recommendations = []

        language = repo_info.get("language", "")
        if language == "Python":
            recommendations.append({
                "category": "architecture",
                "suggestion": "建议使用 pyproject.toml 管理依赖，采用 src/ 目录结构",
                "priority": "medium",
            })
            recommendations.append({
                "category": "quality",
                "suggestion": "添加类型注解，使用 mypy 进行静态类型检查",
                "priority": "high",
            })

        elif language == "TypeScript" or language == "JavaScript":
            recommendations.append({
                "category": "architecture",
                "suggestion": "建议使用 monorepo 结构，配置 ESLint 和 Prettier",
                "priority": "high",
            })

        has_tests = any("test" in item["name"].lower() for item in structure)
        if not has_tests:
            recommendations.append({
                "category": "testing",
                "suggestion": "添加单元测试和集成测试，提高代码覆盖率",
                "priority": "high",
            })

        has_ci = any(item["name"] in [".github", ".gitlab-ci.yml", ".travis.yml"] for item in structure)
        if not has_ci:
            recommendations.append({
                "category": "devops",
                "suggestion": "配置 CI/CD 流水线，自动化测试和部署",
                "priority": "medium",
            })

        if focus_area == "security":
            recommendations.extend([
                {"category": "security", "suggestion": "使用 dependabot 自动更新依赖", "priority": "high"},
                {"category": "security", "suggestion": "添加安全扫描工具 (如 Snyk, Safety)", "priority": "medium"},
            ])

        return recommendations


class CodePatternSkill(SkillBase):
    """代码模式分析"""

    @classmethod
    def get_metadata(cls) -> SkillMetadata:
        return SkillMetadata(
            name="code_pattern",
            display_name="代码模式分析",
            description="分析代码模式，提供最佳实践建议",
            version="1.0.0",
            category=SkillCategory.ANALYSIS,
            tags=["code", "pattern", "best-practices"],
            parameters=[
                SkillParameter(
                    name="code",
                    type=SkillParameterType.STRING,
                    description="要分析的代码",
                    required=True,
                ),
                SkillParameter(
                    name="language",
                    type=SkillParameterType.STRING,
                    description="编程语言",
                    required=False,
                    default="auto",
                ),
            ],
            examples=[
                {"code": "def foo(): pass", "language": "python"},
            ],
        )

    async def execute(self, **kwargs) -> SkillResult:
        code = kwargs.get("code", "")
        language = kwargs.get("language", "auto")

        if not code:
            return SkillResult(
                success=False,
                error="请提供要分析的代码",
                error_code="MISSING_CODE",
            )

        patterns = self._detect_patterns(code, language)
        suggestions = self._generate_suggestions(patterns, language)

        return SkillResult(
            success=True,
            data={
                "patterns": patterns,
                "suggestions": suggestions,
                "language": language,
            },
        )

    def _detect_patterns(self, code: str, language: str) -> list[dict]:
        patterns = []

        if "TODO" in code or "FIXME" in code:
            patterns.append({"name": "todo_comments", "description": "代码中包含待办事项注释"})

        if "print(" in code or "console.log" in code:
            patterns.append({"name": "debug_print", "description": "代码中包含调试打印语句"})

        if re.search(r"password\s*=\s*['\"]", code, re.IGNORECASE):
            patterns.append({"name": "hardcoded_secret", "description": "代码中可能包含硬编码的密钥", "severity": "high"})

        if re.search(r"try\s*:", code) or re.search(r"try\s*{", code):
            patterns.append({"name": "error_handling", "description": "代码包含错误处理"})

        return patterns

    def _generate_suggestions(self, patterns: list[dict], language: str) -> list[str]:
        suggestions = []

        for pattern in patterns:
            if pattern["name"] == "debug_print":
                suggestions.append("建议移除调试打印语句，使用日志框架代替")
            elif pattern["name"] == "hardcoded_secret":
                suggestions.append("警告：请使用环境变量或配置文件管理敏感信息")
            elif pattern["name"] == "todo_comments":
                suggestions.append("建议创建 Issue 跟踪待办事项")

        return suggestions
