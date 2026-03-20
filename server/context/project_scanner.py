"""
项目扫描�?- 分析项目结构和特�?
功能�?- 技术栈检测（Python/JS 框架识别�?- 项目结构分析（目录树�?- 依赖解析（requirements.txt / package.json�?- 关键文件识别
- 代码风格分析
- Git 信息获取
"""
from pathlib import Path
from typing import Dict, List, Any, Optional
import json
import re
import logging
from datetime import datetime

from .models import (
    ProjectInfo,
    TechStack,
    FileInfo,
    ProjectStructure,
    GitInfo,
    SymbolInfo,
)

logger = logging.getLogger(__name__)


class ProjectScanner:
    """项目扫描�?""

    # 语言配置文件定义
    LANGUAGE_CONFIGS = {
        "python": {
            "files": ["requirements.txt", "setup.py", "pyproject.toml", "Pipfile"],
            "extensions": [".py", ".pyi"],
            "ignore_patterns": [
                "__pycache__", "*.pyc", "*.pyo", ".git", "venv", ".venv",
                "env", ".env", "dist", "build", "*.egg-info", ".pytest_cache",
                ".mypy_cache", ".ruff_cache", "node_modules"
            ],
            "framework_patterns": {
                "FastAPI": ["fastapi", "uvicorn"],
                "Flask": ["flask"],
                "Django": ["django"],
                "PyTorch": ["torch", "torchvision"],
                "TensorFlow": ["tensorflow"],
                "Transformers": ["transformers"],
                "LangChain": ["langchain"],
            }
        },
        "javascript": {
            "files": ["package.json", "tsconfig.json", "vite.config.ts", "webpack.config.js"],
            "extensions": [".js", ".ts", ".jsx", ".tsx", ".vue", ".svelte"],
            "ignore_patterns": [
                "node_modules", "dist", "build", ".git", "coverage",
                ".next", "nuxt", ".nuxt", "public", "static"
            ],
            "framework_patterns": {
                "React": ["react", "react-dom"],
                "Vue": ["vue"],
                "Angular": ["@angular/core"],
                "Next.js": ["next"],
                "Nuxt.js": ["nuxt"],
                "Svelte": ["svelte"],
                "Ant Design": ["antd", "@ant-design"],
                "Tailwind CSS": ["tailwindcss"],
                "Express": ["express"],
                "NestJS": ["@nestjs"],
            }
        },
        "java": {
            "files": ["pom.xml", "build.gradle", "settings.gradle"],
            "extensions": [".java", ".kt", ".groovy"],
            "ignore_patterns": ["target", "build", ".class", ".gradle", ".idea"],
            "framework_patterns": {
                "Spring Boot": ["spring-boot"],
                "Spring": ["spring"],
            }
        }
    }

    # 关键文件模式
    KEY_FILE_PATTERNS = {
        "main": ["main.py", "main.js", "main.ts", "index.js", "index.ts", "app.py", "app.js"],
        "config": ["config.py", "config.ts", "settings.py", ".env", "config.json", "config.yaml"],
        "model": ["models.py", "models.ts", "schema.py", "schema.ts"],
        "api": ["api.py", "api.ts", "routes.py", "routes.ts", "views.py", "controllers.py"],
        "service": ["services.py", "services.ts", "service.py"],
        "utils": ["utils.py", "utils.ts", "helpers.py", "tools.py"],
        "test": ["test_*.py", "*_test.py", "*.test.ts", "*.test.js", "tests/*.py"],
    }

    # 领域关键�?    DOMAIN_KEYWORDS = {
        "电商": ["shop", "cart", "product", "order", "payment", "store", "mall"],
        "社交": ["user", "friend", "message", "post", "comment", "like", "share"],
        "金融": ["payment", "transaction", "account", "bank", "trade", "stock"],
        "教育": ["course", "student", "lesson", "teacher", "school", "learn"],
        "AI/ML": ["model", "train", "predict", "torch", "tensorflow", "transformer", "llm"],
        "医疗": ["health", "patient", "hospital", "medical", "disease"],
        "通用": []
    }

    def __init__(self, project_path: str):
        """
        初始化项目扫描器

        Args:
            project_path: 项目根路�?        """
        self.project_path = Path(project_path).resolve()
        if not self.project_path.exists():
            raise FileNotFoundError(f"项目路径不存在：{project_path}")

    def scan(self) -> ProjectInfo:
        """
        扫描整个项目

        Returns:
            项目完整信息
        """
        logger.info(f"开始扫描项目：{self.project_path}")

        project_info = ProjectInfo(
            name=self.project_path.name,
            path=str(self.project_path),
            scanned_at=datetime.now().isoformat(),
        )

        # 1. 检测技术栈
        project_info.tech_stack = self._detect_tech_stack()

        # 2. 构建项目结构
        project_info.structure = self._build_structure()

        # 3. 解析依赖
        project_info.dependencies = self._parse_dependencies()

        # 4. 分析代码风格
        project_info.code_style = self._analyze_code_style()

        # 5. 查找关键文件
        project_info.key_files = self._find_key_files()

        # 6. 获取 Git 信息
        project_info.git_info = self._get_git_info()

        # 7. 推断架构模式
        project_info.architecture = self._detect_architecture()

        # 8. 推断项目领域
        project_info.domain = self._detect_domain()

        logger.info(f"项目扫描完成：{project_info.name}")
        logger.info(f"  技术栈：{project_info.tech_stack.language}, {project_info.tech_stack.frameworks}")
        logger.info(f"  架构：{project_info.architecture}, 领域：{project_info.domain}")

        return project_info

    def _detect_tech_stack(self) -> TechStack:
        """检测技术栈"""
        tech_stack = TechStack(language="unknown", frameworks=[], libraries=[], ui_frameworks=[], databases=[])

        detected_languages = []

        for lang, config in self.LANGUAGE_CONFIGS.items():
            # 检查特征文�?            for file in config["files"]:
                if (self.project_path / file).exists():
                    detected_languages.append(lang)

                    # 检测具体框架和�?                    if lang == "javascript":
                        self._detect_js_frameworks(tech_stack)
                    elif lang == "python":
                        self._detect_python_frameworks(tech_stack)
                    elif lang == "java":
                        self._detect_java_frameworks(tech_stack)
                    break

        # 确定主要语言
        if detected_languages:
            # 优先选择更具体的语言
            if "javascript" in detected_languages:
                tech_stack.language = "javascript"
            elif "python" in detected_languages:
                tech_stack.language = "python"
            elif "java" in detected_languages:
                tech_stack.language = "java"
            else:
                tech_stack.language = detected_languages[0]

        # 去重
        tech_stack.frameworks = list(set(tech_stack.frameworks))
        tech_stack.libraries = list(set(tech_stack.libraries))
        tech_stack.ui_frameworks = list(set(tech_stack.ui_frameworks))

        return tech_stack

    def _detect_js_frameworks(self, tech_stack: TechStack):
        """检�?JavaScript 框架"""
        pkg_file = self.project_path / "package.json"
        if not pkg_file.exists():
            return

        try:
            with open(pkg_file, "r", encoding="utf-8") as f:
                pkg = json.load(f)
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}

            for dep_name in deps.keys():
                for framework, patterns in self.LANGUAGE_CONFIGS["javascript"]["framework_patterns"].items():
                    if any(pattern in dep_name for pattern in patterns):
                        if framework in ["React", "Vue", "Angular", "Next.js", "Nuxt.js", "Svelte"]:
                            if framework not in tech_stack.frameworks:
                                tech_stack.frameworks.append(framework)
                        elif framework in ["Ant Design", "Tailwind CSS"]:
                            if framework not in tech_stack.ui_frameworks:
                                tech_stack.ui_frameworks.append(framework)
                        else:
                            if framework not in tech_stack.libraries:
                                tech_stack.libraries.append(framework)
        except Exception as e:
            logger.warning(f"解析 package.json 失败：{e}")

    def _detect_python_frameworks(self, tech_stack: TechStack):
        """检�?Python 框架"""
        # 检�?requirements.txt
        req_file = self.project_path / "requirements.txt"
        if req_file.exists():
            try:
                with open(req_file, "r", encoding="utf-8") as f:
                    content = f.read().lower()

                for framework, patterns in self.LANGUAGE_CONFIGS["python"]["framework_patterns"].items():
                    if any(pattern in content for pattern in patterns):
                        if framework in ["FastAPI", "Flask", "Django"]:
                            if framework not in tech_stack.frameworks:
                                tech_stack.frameworks.append(framework)
                        elif framework in ["PyTorch", "TensorFlow", "Transformers", "LangChain"]:
                            if framework not in tech_stack.libraries:
                                tech_stack.libraries.append(framework)
            except Exception as e:
                logger.warning(f"解析 requirements.txt 失败：{e}")

        # 检�?pyproject.toml
        pyproject_file = self.project_path / "pyproject.toml"
        if pyproject_file.exists():
            try:
                with open(pyproject_file, "r", encoding="utf-8") as f:
                    content = f.read().lower()
                    # 简单检�?                    if "fastapi" in content:
                        tech_stack.frameworks.append("FastAPI")
                    if "flask" in content:
                        tech_stack.frameworks.append("Flask")
            except Exception as e:
                logger.warning(f"解析 pyproject.toml 失败：{e}")

    def _detect_java_frameworks(self, tech_stack: TechStack):
        """检�?Java 框架"""
        pom_file = self.project_path / "pom.xml"
        if pom_file.exists():
            try:
                with open(pom_file, "r", encoding="utf-8") as f:
                    content = f.read().lower()

                for framework, patterns in self.LANGUAGE_CONFIGS["java"]["framework_patterns"].items():
                    if any(pattern in content for pattern in patterns):
                        if framework not in tech_stack.frameworks:
                            tech_stack.frameworks.append(framework)
            except Exception as e:
                logger.warning(f"解析 pom.xml 失败：{e}")

    def _build_structure(self, depth: int = 3) -> Optional[ProjectStructure]:
        """构建项目结构�?""

        def scan_dir(path: Path, current_depth: int) -> ProjectStructure:
            if current_depth > depth:
                return ProjectStructure(
                    name=path.name,
                    type="folder",
                    children=[]
                )

            structure = ProjectStructure(
                name=path.name if path != self.project_path else self.project_path.name,
                type="folder",
                children=[],
                path=str(path.relative_to(self.project_path)) if path != self.project_path else ""
            )

            try:
                for item in sorted(path.iterdir()):
                    # 跳过忽略的模�?                    if self._should_ignore(item):
                        continue

                    if item.is_file():
                        try:
                            rel_path = str(item.relative_to(self.project_path))
                            structure.children.append(ProjectStructure(
                                name=item.name,
                                type="file",
                                path=rel_path,
                                size=item.stat().st_size
                            ))
                        except (PermissionError, OSError):
                            continue
                    else:
                        child = scan_dir(item, current_depth + 1)
                        if child.children:  # 只添加有内容的目�?                            structure.children.append(child)
            except PermissionError:
                pass

            return structure

        return scan_dir(self.project_path, 0)

    def _should_ignore(self, path: Path) -> bool:
        """检查是否应该忽略该路径"""
        path_str = str(path)
        name = path.name

        # 检查所有语言的忽略模�?        for config in self.LANGUAGE_CONFIGS.values():
            for pattern in config["ignore_patterns"]:
                if pattern.startswith("*"):
                    if name.endswith(pattern[1:]):
                        return True
                elif pattern in path_str:
                    return True

        return False

    def _parse_dependencies(self) -> Dict[str, Any]:
        """解析项目依赖"""
        deps = {}

        # Python 依赖
        req_file = self.project_path / "requirements.txt"
        if req_file.exists():
            try:
                with open(req_file, "r", encoding="utf-8") as f:
                    python_deps = []
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            # 提取包名（去掉版本信息）
                            pkg_name = line.split("==")[0].split(">=")[0].split("<=")[0].strip()
                            python_deps.append(pkg_name)
                    deps["python"] = python_deps
            except Exception as e:
                logger.warning(f"解析 requirements.txt 失败：{e}")

        # JavaScript 依赖
        pkg_file = self.project_path / "package.json"
        if pkg_file.exists():
            try:
                with open(pkg_file, "r", encoding="utf-8") as f:
                    pkg = json.load(f)
                    deps["javascript"] = {
                        "dependencies": pkg.get("dependencies", {}),
                        "devDependencies": pkg.get("devDependencies", {})
                    }
            except Exception as e:
                logger.warning(f"解析 package.json 失败：{e}")

        return deps

    def _analyze_code_style(self) -> Dict[str, Any]:
        """分析代码风格"""
        style = {
            "indentation": "space",  # space �?tab
            "quote": "single",  # single �?double
            "line_length": 88,
            "naming_convention": "snake_case"  # snake_case, camelCase, PascalCase
        }

        # 分析 Python 文件
        py_files = list(self.project_path.glob("**/*.py"))[:10]
        if py_files:
            indent_counts = {"space": 0, "tab": 0}
            quote_counts = {"single": 0, "double": 0}

            for py_file in py_files:
                try:
                    with open(py_file, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read(2000)  # 只读取前 2000 字符

                        # 检测缩�?                        lines = content.split("\n")[:50]
                        for line in lines:
                            if line.startswith("    "):
                                indent_counts["space"] += 1
                            elif line.startswith("\t"):
                                indent_counts["tab"] += 1

                        # 检测引�?                        if content.count("'") > content.count('"'):
                            quote_counts["single"] += 1
                        else:
                            quote_counts["double"] += 1
                except (PermissionError, OSError):
                    continue

            style["indentation"] = max(indent_counts, key=indent_counts.get)
            style["quote"] = max(quote_counts, key=quote_counts.get)

        # 分析 JS/TS 文件
        js_files = list(self.project_path.glob("**/*.{js,ts,tsx}"))[:10]
        if js_files:
            quote_counts = {"single": 0, "double": 0}

            for js_file in js_files:
                try:
                    with open(js_file, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read(2000)
                        if content.count("'") > content.count('"'):
                            quote_counts["single"] += 1
                        else:
                            quote_counts["double"] += 1
                except (PermissionError, OSError):
                    continue

            style["quote"] = max(quote_counts, key=quote_counts.get)

        return style

    def _find_key_files(self) -> List[FileInfo]:
        """查找关键文件"""
        key_files = []

        for category, patterns in self.KEY_FILE_PATTERNS.items():
            for pattern in patterns:
                try:
                    # 处理通配符模�?                    if "*" in pattern:
                        matches = list(self.project_path.glob(f"**/{pattern}"))
                    else:
                        matches = list(self.project_path.glob(f"**/{pattern}"))

                    for match in matches[:3]:  # 每个模式最�?3 个文�?                        try:
                            rel_path = str(match.relative_to(self.project_path))
                            file_info = FileInfo(
                                path=rel_path,
                                name=match.name,
                                size=match.stat().st_size,
                                language=self._detect_language(match),
                            )
                            key_files.append(file_info)
                        except (PermissionError, OSError):
                            continue
                except Exception:
                    continue

        return key_files

    def _detect_language(self, file_path: Path) -> str:
        """检测文件语言"""
        ext = file_path.suffix.lower()

        lang_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".jsx": "javascript",
            ".tsx": "typescript",
            ".vue": "javascript",
            ".java": "java",
            ".kt": "kotlin",
            ".go": "go",
            ".rs": "rust",
            ".rb": "ruby",
            ".php": "php",
            ".cs": "csharp",
            ".cpp": "cpp",
            ".c": "c",
            ".h": "c",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".json": "json",
            ".xml": "xml",
            ".md": "markdown",
            ".sql": "sql",
            ".sh": "bash",
        }

        return lang_map.get(ext, "text")

    def _get_git_info(self) -> GitInfo:
        """获取 Git 信息"""
        git_info = GitInfo(is_git_repo=False)

        git_dir = self.project_path / ".git"
        if not git_dir.exists():
            return git_info

        try:
            import git

            repo = git.Repo(self.project_path)
            git_info.is_git_repo = True
            git_info.branch = repo.active_branch.name if repo.active_branch else None

            if repo.head.commit:
                git_info.last_commit = repo.head.commit.message.strip()
                git_info.last_commit_date = repo.head.commit.committed_datetime.isoformat()

            if repo.remotes and repo.remotes.origin:
                git_info.remote_url = repo.remotes.origin.url
        except ImportError:
            logger.warning("GitPython 未安装，无法获取 Git 信息")
        except Exception as e:
            logger.warning(f"获取 Git 信息失败：{e}")

        return git_info

    def _detect_architecture(self) -> str:
        """检测架构模�?""
        structure = self._build_structure(depth=2)
        if not structure:
            return "Unknown"

        dir_names = [child.name for child in structure.children if child.type == "folder"]

        # MVC 模式
        if any(name in dir_names for name in ["controllers", "views", "models"]):
            return "MVC"

        # 分层架构
        if any(name in dir_names for name in ["services", "controllers", "repositories"]):
            return "Layered"

        # 微服务（多个独立服务目录�?        service_like_dirs = [
            name for name in dir_names
            if any(kw in name.lower() for kw in ["service", "api", "app", "micro"])
        ]
        if len(service_like_dirs) > 3:
            return "Microservices"

        # 前后端分�?        has_frontend = any(name in dir_names for name in ["client", "frontend", "web", "src"])
        has_backend = any(name in dir_names for name in ["server", "backend", "api"])
        if has_frontend and has_backend:
            return "Frontend/Backend Separated"

        return "Monolithic"

    def _detect_domain(self) -> str:
        """检测项目领�?""
        # 收集所有文本用于关键词匹配
        all_text = []

        # 关键文件�?        for key_file in self._find_key_files():
            all_text.append(key_file.name.lower())

        # 依赖�?        deps = self._parse_dependencies()
        for lang, lang_deps in deps.items():
            if isinstance(lang_deps, list):
                all_text.extend([d.lower() for d in lang_deps])
            elif isinstance(lang_deps, dict):
                for dep_list in lang_deps.values():
                    if isinstance(dep_list, dict):
                        all_text.extend([k.lower() for k in dep_list.keys()])

        all_text_str = " ".join(all_text)

        # 匹配领域关键�?        for domain, keywords in self.DOMAIN_KEYWORDS.items():
            if keywords and any(kw in all_text_str for kw in keywords):
                return domain

        return "通用"
