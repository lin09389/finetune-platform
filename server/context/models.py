"""
项目上下文数据模型
"""
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TechStackType(str, Enum):
    """技术栈类型"""
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    JAVA = "java"
    GO = "go"
    RUST = "rust"
    UNKNOWN = "unknown"


class SymbolType(str, Enum):
    """符号类型"""
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    VARIABLE = "variable"
    IMPORT = "import"
    COMPONENT = "component"
    CONSTANT = "constant"


class SymbolInfo(BaseModel):
    """代码符号信息"""
    type: str = Field(..., description="符号类型：class/function/component/method")
    name: str = Field(..., description="符号名称")
    line: int = Field(..., description="行号")
    file_path: str | None = Field(None, description="所属文件路径")
    docstring: str | None = Field(None, description="文档字符串")
    parameters: list[str] | None = Field(None, description="函数参数列表")


class FileInfo(BaseModel):
    """文件信息"""
    path: str = Field(..., description="文件相对路径")
    name: str = Field(..., description="文件名")
    size: int = Field(..., description="文件大小（字节）")
    line_count: int = Field(default=0, description="代码行数")
    language: str = Field(default="text", description="编程语言")
    symbols: list[SymbolInfo] = Field(default_factory=list, description="包含的符号")
    summary: str | None = Field(None, description="文件摘要")
    embedding: list[float] | None = Field(None, description="向量化表示")
    updated_at: str | None = Field(None, description="最后修改时间")


class TechStack(BaseModel):
    """技术栈信息"""
    language: str = Field(..., description="主要语言：python/javascript/java")
    frameworks: list[str] = Field(default_factory=list, description="框架列表")
    libraries: list[str] = Field(default_factory=list, description="关键库列表")
    ui_frameworks: list[str] = Field(default_factory=list, description="UI 框架")
    databases: list[str] = Field(default_factory=list, description="数据库")


class ProjectStructure(BaseModel):
    """项目结构"""
    name: str = Field(..., description="项目名称")
    type: str = Field(default="folder", description="类型：file/folder")
    children: list["ProjectStructure"] = Field(default_factory=list, description="子项")
    path: str | None = Field(None, description="相对路径")
    size: int | None = Field(None, description="文件大小")


class GitInfo(BaseModel):
    """Git 仓库信息"""
    is_git_repo: bool = Field(default=False, description="是否是 Git 仓库")
    branch: str | None = Field(None, description="当前分支")
    last_commit: str | None = Field(None, description="最后提交信息")
    last_commit_date: str | None = Field(None, description="最后提交时间")
    remote_url: str | None = Field(None, description="远程仓库 URL")


class ProjectInfo(BaseModel):
    """项目完整信息"""
    name: str = Field(..., description="项目名称")
    path: str = Field(..., description="项目根路径")
    tech_stack: TechStack = Field(
        default_factory=lambda: TechStack(
            language="unknown",
            frameworks=[],
            libraries=[],
            ui_frameworks=[],
            databases=[]
        ),
        description="技术栈"
    )
    structure: ProjectStructure | None = Field(None, description="项目结构树")
    dependencies: dict[str, Any] = Field(default_factory=dict, description="依赖列表")
    files: list[FileInfo] = Field(default_factory=list, description="文件列表")
    key_files: list[FileInfo] = Field(default_factory=list, description="关键文件")
    git_info: GitInfo = Field(default_factory=GitInfo, description="Git 信息")
    architecture: str | None = Field(None, description="架构模式：MVC/Microservices 等")
    domain: str | None = Field(None, description="项目领域：电商/社交/金融/AI 等")
    code_style: dict[str, Any] = Field(default_factory=dict, description="代码风格")
    scanned_at: str | None = Field(None, description="扫描时间")
    indexed_at: str | None = Field(None, description="索引时间")



    def get(self, key: str, default: Any = None) -> Any:
        if key == "tech_stack":
            return [self.tech_stack.language, *self.tech_stack.frameworks]
        if key == "file_count":
            return len(self.files) + len(self.key_files)
        return getattr(self, key, default)

class ContextResult(BaseModel):
    """上下文检索结果"""
    type: str = Field(..., description="结果类型：file/project/symbol")
    path: str | None = Field(None, description="文件路径")
    source_file: str | None = Field(None, description="源文件")
    relevance: float = Field(default=0.0, description="相关度分数")
    score: float = Field(default=0.0, description="匹配分数")
    summary: str | None = Field(None, description="摘要")
    content: str | None = Field(None, description="文件内容片段")
    symbols: list[SymbolInfo] = Field(default_factory=list, description="相关符号")
    tech_stack: list[str] | None = Field(None, description="技术栈（项目级结果）")
    architecture: str | None = Field(None, description="架构（项目级结果）")
    domain: str | None = Field(None, description="领域（项目级结果）")


class CodeSnippet(BaseModel):
    """代码片段"""
    file_path: str = Field(..., description="文件路径")
    content: str = Field(..., description="代码内容")
    start_line: int = Field(default=0, description="起始行")
    end_line: int = Field(default=0, description="结束行")
    language: str = Field(default="text", description="语言")


class CodeCompletionContext(BaseModel):
    """代码补全上下文"""
    current_file: str | None = Field(None, description="当前文件摘要")
    related_symbols: list[SymbolInfo] = Field(default_factory=list, description="相关符号")
    imports: list[str] = Field(default_factory=list, description="导入的模块")
    project_context: dict[str, Any] = Field(default_factory=dict, description="项目上下文")


class IndexResult(BaseModel):
    """索引结果"""
    project_path: str = Field(..., description="项目路径")
    files_indexed: int = Field(default=0, description="已索引文件数")
    symbols_indexed: int = Field(default=0, description="已索引符号数")
    vectors_created: int = Field(default=0, description="创建的向量数")
    duration_ms: float = Field(default=0.0, description="索引耗时（毫秒）")
    errors: list[str] = Field(default_factory=list, description="错误列表")


class RetrievalResult(BaseModel):
    """检索结果"""
    query: str = Field(..., description="查询文本")
    results: list[ContextResult] = Field(default_factory=list, description="结果列表")
    total: int = Field(default=0, description="总结果数")
    duration_ms: float = Field(default=0.0, description="检索耗时（毫秒）")


class ContextInfo(BaseModel):
    """上下文信息模型"""
    project_name: str = Field(default="", description="项目名称")
    project_path: str = Field(default="", description="项目路径")
    tech_stack: TechStack | None = Field(default=None, description="技术栈")
    key_files: list[FileInfo] = Field(default_factory=list, description="关键文件")
    symbols: list[SymbolInfo] = Field(default_factory=list, description="代码符号")
    summary: str | None = Field(default=None, description="项目摘要")
    last_updated: str | None = Field(default=None, description="最后更新时间")
