"""
项目上下文数据模�?"""
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime


class SymbolInfo(BaseModel):
    """代码符号信息"""
    type: str = Field(..., description="符号类型：class/function/component/method")
    name: str = Field(..., description="符号名称")
    line: int = Field(..., description="行号")
    file_path: Optional[str] = Field(None, description="所属文件路�?)
    docstring: Optional[str] = Field(None, description="文档字符�?)
    parameters: Optional[List[str]] = Field(None, description="函数参数列表")


class FileInfo(BaseModel):
    """文件信息"""
    path: str = Field(..., description="文件相对路径")
    name: str = Field(..., description="文件�?)
    size: int = Field(..., description="文件大小（字节）")
    lines: int = Field(default=0, description="代码行数")
    language: str = Field(default="text", description="编程语言")
    symbols: List[SymbolInfo] = Field(default_factory=list, description="包含的符�?)
    summary: Optional[str] = Field(None, description="文件摘要")
    embedding: Optional[List[float]] = Field(None, description="向量化表�?)
    updated_at: Optional[str] = Field(None, description="最后修改时�?)


class TechStack(BaseModel):
    """技术栈信息"""
    language: str = Field(..., description="主要语言：python/javascript/java")
    frameworks: List[str] = Field(default_factory=list, description="框架列表")
    libraries: List[str] = Field(default_factory=list, description="关键库列�?)
    ui_frameworks: List[str] = Field(default_factory=list, description="UI 框架")
    databases: List[str] = Field(default_factory=list, description="数据�?)


class ProjectStructure(BaseModel):
    """项目结构"""
    name: str = Field(..., description="项目名称")
    type: str = Field(default="folder", description="类型：file/folder")
    children: List["ProjectStructure"] = Field(default_factory=list, description="子项")
    path: Optional[str] = Field(None, description="相对路径")
    size: Optional[int] = Field(None, description="文件大小")


class GitInfo(BaseModel):
    """Git 仓库信息"""
    is_git_repo: bool = Field(default=False, description="是否�?Git 仓库")
    branch: Optional[str] = Field(None, description="当前分支")
    last_commit: Optional[str] = Field(None, description="最后提交信�?)
    last_commit_date: Optional[str] = Field(None, description="最后提交时�?)
    remote_url: Optional[str] = Field(None, description="远程仓库 URL")


class ProjectInfo(BaseModel):
    """项目完整信息"""
    name: str = Field(..., description="项目名称")
    path: str = Field(..., description="项目根路�?)
    tech_stack: TechStack = Field(default_factory=lambda: TechStack(
        language="unknown", frameworks=[], libraries=[], ui_frameworks=[], databases=[]
    ), description="技术栈")
    structure: Optional[ProjectStructure] = Field(None, description="项目结构�?)
    dependencies: Dict[str, Any] = Field(default_factory=dict, description="依赖列表")
    key_files: List[FileInfo] = Field(default_factory=list, description="关键文件")
    git_info: GitInfo = Field(default_factory=GitInfo, description="Git 信息")
    architecture: Optional[str] = Field(None, description="架构模式：MVC/Microservices �?)
    domain: Optional[str] = Field(None, description="项目领域：电�?社交/金融/AI �?)
    code_style: Dict[str, Any] = Field(default_factory=dict, description="代码风格")
    scanned_at: Optional[str] = Field(None, description="扫描时间")
    indexed_at: Optional[str] = Field(None, description="索引时间")


class ContextResult(BaseModel):
    """上下文检索结�?""
    type: str = Field(..., description="结果类型：file/project/symbol")
    path: Optional[str] = Field(None, description="文件路径")
    relevance: float = Field(default=0.0, description="相关度分�?)
    summary: Optional[str] = Field(None, description="摘要")
    symbols: List[SymbolInfo] = Field(default_factory=list, description="相关符号")
    content: Optional[str] = Field(None, description="文件内容片段")
    tech_stack: Optional[List[str]] = Field(None, description="技术栈（项目级结果�?)
    architecture: Optional[str] = Field(None, description="架构（项目级结果�?)
    domain: Optional[str] = Field(None, description="领域（项目级结果�?)


class CodeCompletionContext(BaseModel):
    """代码补全上下�?""
    current_file: Optional[str] = Field(None, description="当前文件摘要")
    related_symbols: List[SymbolInfo] = Field(default_factory=list, description="相关符号")
    imports: List[str] = Field(default_factory=list, description="导入的模�?)
    project_context: Dict[str, Any] = Field(default_factory=dict, description="项目上下�?)
