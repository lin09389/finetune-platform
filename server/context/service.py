# -*- coding: utf-8 -*-
"""
项目上下文服务
封装项目扫描、索引、检索的完整流程
"""
from typing import Dict, List, Any, Optional
import logging
from pathlib import Path

from .models import ProjectInfo, ContextResult, CodeSnippet, FileInfo, SymbolInfo
from .project_scanner import ProjectScanner
from .context_retriever import ContextRetriever

logger = logging.getLogger(__name__)


class CodeIndexer:
    """代码索引器（简化版）"""
    
    def __init__(self, embedder=None, vector_store=None):
        self.embedder = embedder
        self.vector_store = vector_store
        self._indexed_files: Dict[str, List[str]] = {}
    
    def index_project(self, project_info: ProjectInfo, force_reindex: bool = False) -> Dict[str, Any]:
        """索引项目"""
        indexed_count = 0
        errors = []
        
        for file_info in project_info.files:
            try:
                self._indexed_files.setdefault(project_info.path, []).append(file_info.path)
                indexed_count += 1
            except Exception as e:
                errors.append(f"{file_info.path}: {str(e)}")
        
        return {
            "files_indexed": indexed_count,
            "errors": errors
        }
    
    def remove_project(self, project_path: str):
        """移除项目索引"""
        if project_path in self._indexed_files:
            del self._indexed_files[project_path]
    
    def get_stats(self, project_path: str) -> Dict[str, Any]:
        """获取索引统计"""
        return {
            "indexed_files": len(self._indexed_files.get(project_path, []))
        }


class ContextService:
    """项目上下文服务"""
    
    def __init__(self, embedder=None, vector_store=None):
        self.projects: Dict[str, ProjectInfo] = {}
        self.scanner = ProjectScanner()
        self.indexer = CodeIndexer(embedder=embedder, vector_store=vector_store)
        self.retriever = None
    
    def scan_project(self, project_path: str) -> ProjectInfo:
        """扫描项目"""
        project_info = self.scanner.scan(project_path)
        self.projects[project_path] = project_info
        return project_info
    
    def index_project(
        self,
        project_path: str,
        force_reindex: bool = False
    ) -> Dict[str, Any]:
        """索引项目"""
        if project_path not in self.projects:
            self.scan_project(project_path)
        
        project_info = self.projects[project_path]
        return self.indexer.index_project(project_info, force_reindex)
    
    def retrieve(
        self,
        query: str,
        project_path: Optional[str] = None,
        top_k: int = 5
    ) -> List[ContextResult]:
        """检索上下文"""
        if self.retriever:
            return self.retriever.retrieve(query, top_k)
        
        results = []
        if project_path and project_path in self.projects:
            project_info = self.projects[project_path]
            for file_info in project_info.key_files[:top_k]:
                results.append(ContextResult(
                    type="file",
                    path=file_info.path,
                    source_file=file_info.name,
                    relevance=0.8,
                    score=0.8,
                    content=file_info.summary or "",
                    symbols=file_info.symbols
                ))
        return results
    
    def get_context_for_chat(
        self,
        query: str,
        project_path: Optional[str] = None,
        max_length: int = 2000
    ) -> str:
        """获取用于聊天的上下文"""
        results = self.retrieve(query, project_path, top_k=10)
        
        if not results:
            return ""
        
        context_parts = []
        current_length = 0
        
        for result in results:
            content = result.content or ""
            if current_length + len(content) > max_length:
                break
            
            context_parts.append(f"[{result.source_file}]\n{content}")
            current_length += len(content)
        
        return "\n\n".join(context_parts)
    
    def list_projects(self) -> List[Dict[str, Any]]:
        """列出所有项目"""
        return [
            {
                "path": path,
                "name": info.name,
                "tech_stack": [info.tech_stack.language] if info.tech_stack else [],
                "files_count": len(info.files),
            }
            for path, info in self.projects.items()
        ]
    
    def remove_project(self, project_path: str) -> bool:
        """移除项目"""
        if project_path in self.projects:
            del self.projects[project_path]
            self.indexer.remove_project(project_path)
            return True
        return False
    
    def get_project_stats(self, project_path: str) -> Optional[Dict[str, Any]]:
        """获取项目统计信息"""
        if project_path not in self.projects:
            return None
        
        project_info = self.projects[project_path]
        index_stats = self.indexer.get_stats(project_path)
        
        return {
            "name": project_info.name,
            "path": project_path,
            "tech_stack": [project_info.tech_stack.language] if project_info.tech_stack else [],
            "files_count": len(project_info.files),
            "total_lines": sum(f.line_count for f in project_info.files),
            "index_stats": index_stats,
        }


_service_instance: Optional[ContextService] = None


def get_context_service(embedder=None, vector_store=None) -> ContextService:
    """获取上下文服务实例"""
    global _service_instance
    if _service_instance is None:
        _service_instance = ContextService(
            embedder=embedder,
            vector_store=vector_store
        )
    return _service_instance


def reset_context_service(embedder=None, vector_store=None) -> ContextService:
    """重置上下文服务实例"""
    global _service_instance
    _service_instance = ContextService(
        embedder=embedder,
        vector_store=vector_store
    )
    return _service_instance
