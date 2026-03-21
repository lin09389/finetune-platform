# -*- coding: utf-8 -*-
"""
上下文检索器 - 智能检索相关代码
功能：
- 语义搜索（向量相似度）
- 相关文件检索
- 代码补全上下文
- 项目级上下文注入
"""
from typing import List, Dict, Any, Optional
import logging
import re

from .models import ContextResult, CodeCompletionContext, SymbolInfo

logger = logging.getLogger(__name__)


class ContextRetriever:
    """上下文检索器"""

    def __init__(self, embedder=None, vector_store=None, project_info: Optional[Dict] = None):
        """
        初始化上下文检索器

        Args:
            embedder: 向量化器实例
            vector_store: 向量存储实例
            project_info: 项目信息（可选）
        """
        self.embedder = embedder
        self.vector_store = vector_store
        self.project_info = project_info or {}

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        collection_name: Optional[str] = None,
        filter_metadata: Optional[Dict] = None
    ) -> List[ContextResult]:
        """
        检索与查询最相关的上下文

        Args:
            query: 查询文本
            top_k: 返回结果数量
            collection_name: 集合名称（可选）
            filter_metadata: 元数据过滤条件

        Returns:
            上下文结果列表
        """
        if not self.embedder or not self.vector_store:
            logger.warning("向量存储或嵌入器未初始化")
            return []

        if not collection_name:
            collections = self.vector_store.list_collections()
            if not collections:
                logger.warning("没有可用的向量集合")
                return []
            collection_name = collections[0]

        try:
            query_embedding = self.embedder.embed_single(query)

            results = self.vector_store.search(
                collection_name=collection_name,
                query_embedding=query_embedding,
                top_k=top_k,
                filter_metadata=filter_metadata
            )

            context_results = []
            for result in results:
                metadata = result.get("metadata", {})
                path = metadata.get("path", "")

                existing = next(
                    (r for r in context_results if r.path == path),
                    None
                )

                if existing:
                    if result.get("content"):
                        existing.content = f"{existing.content}\n...\n{result['content']}"
                else:
                    context_results.append(ContextResult(
                        type="file",
                        path=path,
                        relevance=result.get("score", 0.0),
                        summary=result.get("content", "")[:500],
                        content=result.get("content"),
                        symbols=self._extract_symbols_from_metadata(metadata)
                    ))

            if self.project_info:
                context_results.append(ContextResult(
                    type="project",
                    tech_stack=self.project_info.get("tech_stack", {}).get("frameworks", []),
                    architecture=self.project_info.get("architecture"),
                    domain=self.project_info.get("domain")
                ))

            context_results.sort(key=lambda x: x.relevance, reverse=True)

            return context_results[:top_k + 1]

        except Exception as e:
            logger.error(f"检索上下文失败：{e}")
            return []

    def retrieve_for_code_completion(
        self,
        file_path: str,
        content: str,
        cursor_position: int,
        collection_name: Optional[str] = None
    ) -> CodeCompletionContext:
        """
        为代码补全检索上下文

        Args:
            file_path: 文件路径
            content: 当前文件内容
            cursor_position: 光标位置
            collection_name: 集合名称

        Returns:
            代码补全上下文
        """
        before_cursor = content[:cursor_position]
        current_line = before_cursor.split("\n")[-1]

        match = re.search(r'(\w+)$', current_line)
        current_symbol = match.group(1) if match else None

        related_symbols = []
        imports = self._parse_imports(content)

        if current_symbol and collection_name and self.embedder and self.vector_store:
            try:
                query_embedding = self.embedder.embed_single(current_symbol)
                results = self.vector_store.search(
                    collection_name=collection_name,
                    query_embedding=query_embedding,
                    top_k=5
                )

                for result in results:
                    metadata = result.get("metadata", {})
                    symbol_name = metadata.get("symbol_name", "")

                    if symbol_name and symbol_name != current_symbol:
                        related_symbols.append(SymbolInfo(
                            type=metadata.get("symbol_type", "unknown"),
                            name=symbol_name,
                            line=metadata.get("start_line", 0),
                            file_path=metadata.get("path", "")
                        ))
            except Exception as e:
                logger.warning(f"搜索相关符号失败：{e}")

        project_context = {}
        if self.project_info:
            project_context = {
                "tech_stack": self.project_info.get("tech_stack", {}),
                "architecture": self.project_info.get("architecture"),
                "code_style": self.project_info.get("code_style", {})
            }

        return CodeCompletionContext(
            current_file=self.project_info.get("name", ""),
            related_symbols=related_symbols,
            imports=imports,
            project_context=project_context
        )

    def retrieve_by_path(
        self,
        path: str,
        collection_name: Optional[str] = None
    ) -> Optional[ContextResult]:
        """
        根据路径检索文件

        Args:
            path: 文件路径
            collection_name: 集合名称

        Returns:
            上下文结果
        """
        if not self.vector_store:
            return None

        if not collection_name:
            collections = self.vector_store.list_collections()
            if not collections:
                return None
            collection_name = collections[0]

        try:
            results = self.vector_store.search(
                collection_name=collection_name,
                query_embedding=[0.0] * 768,
                top_k=1,
                filter_metadata={"path": path}
            )

            if results:
                result = results[0]
                metadata = result.get("metadata", {})

                return ContextResult(
                    type="file",
                    path=path,
                    relevance=1.0,
                    summary=result.get("content", "")[:500],
                    content=result.get("content"),
                    symbols=self._extract_symbols_from_metadata(metadata)
                )
        except Exception as e:
            logger.warning(f"检索文件失败 {path}: {e}")

        return None

    def retrieve_by_symbol(
        self,
        symbol_name: str,
        symbol_type: Optional[str] = None,
        collection_name: Optional[str] = None
    ) -> List[ContextResult]:
        """
        根据符号名检索

        Args:
            symbol_name: 符号名称
            symbol_type: 符号类型（可选）
            collection_name: 集合名称

        Returns:
            上下文结果列表
        """
        if not self.embedder or not self.vector_store:
            return []

        if not collection_name:
            collections = self.vector_store.list_collections()
            if not collections:
                return []
            collection_name = collections[0]

        try:
            query_embedding = self.embedder.embed_single(symbol_name)

            results = self.vector_store.search(
                collection_name=collection_name,
                query_embedding=query_embedding,
                top_k=10
            )

            context_results = []
            for result in results:
                metadata = result.get("metadata", {})

                meta_symbol_name = metadata.get("symbol_name", "")
                if meta_symbol_name.lower() == symbol_name.lower():
                    if symbol_type and metadata.get("symbol_type") != symbol_type:
                        continue

                    context_results.append(ContextResult(
                        type="symbol",
                        path=metadata.get("path", ""),
                        relevance=result.get("score", 0.0),
                        summary=result.get("content", "")[:300],
                        content=result.get("content"),
                        symbols=[SymbolInfo(
                            type=metadata.get("symbol_type", "unknown"),
                            name=meta_symbol_name,
                            line=metadata.get("start_line", 0),
                            file_path=metadata.get("path", "")
                        )]
                    ))

            return context_results

        except Exception as e:
            logger.error(f"检索符号失败：{e}")
            return []

    def format_context_for_prompt(
        self,
        results: List[ContextResult],
        max_length: int = 2000
    ) -> str:
        """
        格式化上下文用于 prompt

        Args:
            results: 检索结果
            max_length: 最大长度

        Returns:
            格式化的上下文字符串
        """
        parts = []

        for result in results:
            if result.type == "project":
                project_parts = []
                if result.tech_stack:
                    project_parts.append(f"技术栈：{', '.join(result.tech_stack)}")
                if result.architecture:
                    project_parts.append(f"架构：{result.architecture}")
                if result.domain:
                    project_parts.append(f"领域：{result.domain}")

                if project_parts:
                    parts.append("项目信息:\n" + "\n".join(project_parts))

            elif result.type == "file":
                file_info = f"文件：{result.path}"
                if result.summary:
                    file_info += f"\n摘要：{result.summary[:200]}"

                parts.append(file_info)

            elif result.type == "symbol":
                for symbol in result.symbols:
                    parts.append(f"{symbol.type} {symbol.name} (第{symbol.line}行)")

        context = "\n\n".join(parts)

        if len(context) > max_length:
            context = context[:max_length] + "\n...(已截断)"

        return context

    def _extract_symbols_from_metadata(self, metadata: Dict) -> List[SymbolInfo]:
        """从元数据提取符号信息"""
        symbols = []

        symbol_type = metadata.get("symbol_type")
        symbol_name = metadata.get("symbol_name")
        start_line = metadata.get("start_line", 0)
        path = metadata.get("path", "")

        if symbol_type and symbol_name:
            symbols.append(SymbolInfo(
                type=symbol_type,
                name=symbol_name,
                line=start_line,
                file_path=path
            ))

        return symbols

    def _parse_imports(self, content: str) -> List[str]:
        """解析导入语句"""
        imports = []

        for match in re.finditer(r'^import\s+([\w.]+)', content, re.MULTILINE):
            imports.append(match.group(1))
        for match in re.finditer(r'^from\s+([\w.]+)\s+import', content, re.MULTILINE):
            imports.append(match.group(1))

        for match in re.finditer(r'import\s+.*?\s+from\s+[\'"]([^\'"]+)[\'"]', content):
            imports.append(match.group(1))

        return list(set(imports))


_retrievers: Dict[str, ContextRetriever] = {}


def get_context_retriever(
    embedder=None,
    vector_store=None,
    project_info: Optional[Dict] = None,
    name: str = "default"
) -> ContextRetriever:
    """获取上下文检索器实例"""
    if name not in _retrievers:
        _retrievers[name] = ContextRetriever(
            embedder=embedder,
            vector_store=vector_store,
            project_info=project_info
        )
    return _retrievers[name]
