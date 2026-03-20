"""
项目上下文服�?
封装项目扫描、索引、检索的完整流程
"""
from typing import Dict, List, Any, Optional
import logging
from pathlib import Path

from .models import ProjectInfo, ContextResult, CodeCompletionContext
from .project_scanner import ProjectScanner
from .code_indexer import CodeIndexer
from .context_retriever import ContextRetriever, get_context_retriever

logger = logging.getLogger(__name__)


class ContextService:
    """项目上下文服�?""

    def __init__(self, embedder=None, vector_store=None):
        """
        初始化服�?
        Args:
            embedder: 向量化器实例
            vector_store: 向量存储实例
        """
        self.embedder = embedder
        self.vector_store = vector_store

        # 缓存
        self.projects: Dict[str, ProjectInfo] = {}  # path -> ProjectInfo
        self.indices: Dict[str, Dict] = {}  # collection_name -> index_info
        self.retrievers: Dict[str, ContextRetriever] = {}

    def scan_project(self, project_path: str) -> ProjectInfo:
        """
        扫描项目

        Args:
            project_path: 项目路径

        Returns:
            项目信息
        """
        logger.info(f"扫描项目：{project_path}")

        scanner = ProjectScanner(project_path)
        project_info = scanner.scan()

        # 缓存
        self.projects[project_path] = project_info

        return project_info

    def index_project(
        self,
        project_path: str,
        force_reindex: bool = False
    ) -> Dict[str, Any]:
        """
        索引项目

        Args:
            project_path: 项目路径
            force_reindex: 是否强制重新索引

        Returns:
            索引摘要
        """
        # 检查是否已扫描
        if project_path not in self.projects:
            self.scan_project(project_path)

        project_info = self.projects[project_path]

        # 生成集合名称
        import hashlib
        path_hash = hashlib.md5(project_path.encode()).hexdigest()[:12]
        collection_name = f"project_{path_hash}"

        # 检查是否已索引
        if collection_name in self.indices and not force_reindex:
            logger.info(f"项目已索引：{collection_name}")
            return self.indices[collection_name]

        # 创建索引�?        indexer = CodeIndexer(
            embedder=self.embedder,
            vector_store=self.vector_store
        )

        # 构建索引
        index_summary = indexer.build_index(
            project_info=project_info,
            collection_name=collection_name
        )

        # 缓存
        self.indices[collection_name] = index_summary

        # 创建检索器
        self.retrievers[collection_name] = get_context_retriever(
            embedder=self.embedder,
            vector_store=self.vector_store,
            project_info=project_info.model_dump(),
            name=collection_name
        )

        logger.info(f"项目索引完成：{collection_name}")

        return index_summary

    def retrieve(
        self,
        query: str,
        project_path: Optional[str] = None,
        top_k: int = 5
    ) -> List[ContextResult]:
        """
        检索上下文

        Args:
            query: 查询文本
            project_path: 项目路径（可选，默认使用第一个）
            top_k: 返回结果数量

        Returns:
            上下文结果列�?        """
        # 确定项目
        if not project_path:
            if not self.projects:
                logger.warning("没有已扫描的项目")
                return []
            project_path = list(self.projects.keys())[0]

        # 确保已索�?        if project_path not in self.projects:
            self.index_project(project_path)

        # 生成集合�?        import hashlib
        path_hash = hashlib.md5(project_path.encode()).hexdigest()[:12]
        collection_name = f"project_{path_hash}"

        # 获取检索器
        if collection_name not in self.retrievers:
            project_info = self.projects.get(project_path)
            self.retrievers[collection_name] = get_context_retriever(
                embedder=self.embedder,
                vector_store=self.vector_store,
                project_info=project_info.model_dump() if project_info else None,
                name=collection_name
            )

        retriever = self.retrievers[collection_name]

        # 检�?        results = retriever.retrieve(
            query=query,
            top_k=top_k,
            collection_name=collection_name
        )

        return results

    def get_context_for_chat(
        self,
        query: str,
        project_path: Optional[str] = None,
        max_length: int = 2000
    ) -> str:
        """
        获取聊天用的上下�?
        Args:
            query: 用户问题
            project_path: 项目路径
            max_length: 最大长�?
        Returns:
            格式化的上下文字符串
        """
        results = self.retrieve(query, project_path, top_k=5)

        if not results:
            return ""

        # 获取检索器来格式化
        import hashlib
        if project_path:
            path_hash = hashlib.md5(project_path.encode()).hexdigest()[:12]
            collection_name = f"project_{path_hash}"
            retriever = self.retrievers.get(collection_name)
        else:
            retriever = next(iter(self.retrievers.values()), None)

        if retriever:
            return retriever.format_context_for_prompt(results, max_length)

        # 简单格式化
        parts = []
        for result in results:
            if result.type == "file" and result.path:
                parts.append(f"相关文件：{result.path}")
            elif result.type == "project":
                if result.tech_stack:
                    parts.append(f"技术栈：{', '.join(result.tech_stack)}")
                if result.architecture:
                    parts.append(f"架构：{result.architecture}")

        return "\n".join(parts)

    def list_projects(self) -> List[Dict[str, Any]]:
        """列出已索引的项目"""
        return [
            {
                "name": info.name,
                "path": info.path,
                "tech_stack": info.tech_stack.model_dump() if info.tech_stack else {},
                "indexed_at": self.indices.get(
                    f"project_{hashlib.md5(info.path.encode()).hexdigest()[:12]}"
                ).get("updated_at") if f"project_{hashlib.md5(info.path.encode()).hexdigest()[:12]}" in self.indices else None
            }
            for info in self.projects.values()
        ]

    def remove_project(self, project_path: str) -> bool:
        """
        移除项目索引

        Args:
            project_path: 项目路径

        Returns:
            是否成功
        """
        import hashlib
        path_hash = hashlib.md5(project_path.encode()).hexdigest()[:12]
        collection_name = f"project_{path_hash}"

        # 从向量库删除
        try:
            self.vector_store.delete_collection(collection_name)
        except Exception as e:
            logger.warning(f"删除向量集合失败：{e}")

        # 清除缓存
        self.projects.pop(project_path, None)
        self.indices.pop(collection_name, None)
        self.retrievers.pop(collection_name, None)

        logger.info(f"已移除项目：{project_path}")
        return True

    def get_project_stats(self, project_path: str) -> Optional[Dict[str, Any]]:
        """获取项目统计信息"""
        if project_path not in self.projects:
            return None

        import hashlib
        path_hash = hashlib.md5(project_path.encode()).hexdigest()[:12]
        collection_name = f"project_{path_hash}"

        index_info = self.indices.get(collection_name)
        if not index_info:
            return None

        return {
            "name": self.projects[project_path].name,
            "path": project_path,
            "files_indexed": index_info.get("files_indexed", 0),
            "symbols_found": index_info.get("symbols_found", 0),
            "chunks_created": index_info.get("chunks_created", 0),
            "updated_at": index_info.get("updated_at")
        }


# 全局服务实例
_service_instance: Optional[ContextService] = None


def get_context_service(embedder=None, vector_store=None) -> ContextService:
    """获取上下文服务实�?""
    global _service_instance
    if _service_instance is None:
        _service_instance = ContextService(
            embedder=embedder,
            vector_store=vector_store
        )
    return _service_instance


def reset_context_service(embedder=None, vector_store=None) -> ContextService:
    """重置上下文服务实�?""
    global _service_instance
    _service_instance = ContextService(
        embedder=embedder,
        vector_store=vector_store
    )
    return _service_instance
