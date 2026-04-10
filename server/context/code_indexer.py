"""
代码索引器
- 构建代码知识库
功能：
- 索引代码文件
- 提取符号（类、函数、组件）
- 向量化存储
- 增量更新
"""
import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import ProjectInfo, SymbolInfo
from .symbol_extractor import get_symbol_extractor

logger = logging.getLogger(__name__)


class CodeIndexer:
    """代码索引器"""

    DEFAULT_CONFIG = {
        "max_file_size": 1024 * 1024,
        "max_content_length": 10000,
        "supported_extensions": [
            ".py", ".js", ".ts", ".jsx", ".tsx",
            ".java", ".go", ".rs", ".rb", ".php",
            ".vue", ".svelte",
        ],
        "ignore_patterns": [
            "node_modules", "__pycache__", ".git", "venv", ".venv",
            "dist", "build", "target", "coverage", ".next", ".nuxt"
        ]
    }

    def __init__(
        self,
        embedder=None,
        vector_store=None,
        config: dict | None = None
    ):
        """
        初始化代码索引器

        Args:
            embedder: 向量化器实例（复用 RAG 模块）
            vector_store: 向量存储实例（复用 RAG 模块）
            config: 配置字典
        """
        self.config = {**self.DEFAULT_CONFIG, **(config or {})}
        self.embedder = embedder
        self.vector_store = vector_store
        self.symbol_extractor = get_symbol_extractor()
        self.index_cache: dict[str, dict] = {}

    def build_index(
        self,
        project_info: ProjectInfo,
        collection_name: str | None = None
    ) -> dict[str, Any]:
        """
        构建项目索引

        Args:
            project_info: 项目信息
            collection_name: 集合名称（默认：project_{project_name}）
        Returns:
            索引摘要信息
        """
        if not self.embedder or not self.vector_store:
            raise ValueError("需要 embedder 和 vector_store 实例")

        if collection_name is None:
            path_hash = hashlib.md5(project_info.path.encode()).hexdigest()[:12]
            collection_name = f"project_{path_hash}"

        logger.info(f"开始构建索引，集合：{collection_name}")

        index_summary = {
            "collection_name": collection_name,
            "project_name": project_info.name,
            "project_path": project_info.path,
            "files_indexed": 0,
            "symbols_found": 0,
            "chunks_created": 0,
            "updated_at": datetime.now().isoformat()
        }

        all_symbols: list[SymbolInfo] = []
        files_data: dict[str, Any] = {}

        for file_info in project_info.key_files:
            try:
                file_path = Path(project_info.path) / file_info.path
                if file_path.exists():
                    result = self._index_file(
                        file_path=str(file_path),
                        rel_path=file_info.path,
                        collection_name=collection_name
                    )
                    if result:
                        index_summary["files_indexed"] += 1
                        index_summary["symbols_found"] += len(result.get("symbols", []))
                        index_summary["chunks_created"] += result.get("chunks", 0)

                        files_data[file_info.path] = result
                        all_symbols.extend(result.get("symbols", []))
            except Exception as e:
                logger.warning(f"索引文件失败 {file_info.path}: {e}")

        project_path = Path(project_info.path)
        for ext in self.config["supported_extensions"]:
            for file_path in project_path.glob(f"**/*{ext}"):
                if self._should_ignore(file_path):
                    continue

                rel_path = str(file_path.relative_to(project_path))
                if rel_path in files_data:
                    continue

                try:
                    result = self._index_file(
                        file_path=str(file_path),
                        rel_path=rel_path,
                        collection_name=collection_name
                    )
                    if result:
                        index_summary["files_indexed"] += 1
                        index_summary["symbols_found"] += len(result.get("symbols", []))
                        index_summary["chunks_created"] += result.get("chunks", 0)

                        files_data[rel_path] = result
                        all_symbols.extend(result.get("symbols", []))
                except Exception as e:
                    logger.warning(f"索引文件失败 {rel_path}: {e}")

        self.index_cache[collection_name] = {
            "project_info": project_info.model_dump(),
            "files": files_data,
            "symbols": [s.model_dump() for s in all_symbols],
            "summary": index_summary
        }

        logger.info(
            f"索引构建完成：{index_summary['files_indexed']} 个文件，"
            f"{index_summary['symbols_found']} 个符号，"
            f"{index_summary['chunks_created']} 个向量块"
        )

        return index_summary

    def _index_file(
        self,
        file_path: str,
        rel_path: str,
        collection_name: str
    ) -> dict[str, Any] | None:
        """
        索引单个文件

        Args:
            file_path: 文件绝对路径
            rel_path: 相对路径
            collection_name: 集合名称

        Returns:
            索引结果
        """
        path = Path(file_path)

        try:
            file_size = path.stat().st_size
            if file_size > self.config["max_file_size"]:
                logger.debug(f"文件过大，跳过：{rel_path}")
                return None
        except OSError:
            return None

        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception as e:
            logger.warning(f"读取文件失败 {file_path}: {e}")
            return None

        if not content.strip():
            return None

        symbols = self.symbol_extractor.extract(file_path, content)
        summary = self._generate_summary(content, symbols)
        chunks = self._chunk_content(content, symbols)

        chunk_count = 0
        for chunk in chunks:
            try:
                embedding = self.embedder.embed_single(chunk["content"])

                metadata = {
                    "type": "code",
                    "path": rel_path,
                    "file_path": file_path,
                    "language": self._detect_language(path),
                    "symbol_type": chunk.get("symbol_type"),
                    "symbol_name": chunk.get("symbol_name"),
                    "start_line": chunk.get("start_line", 0),
                    "end_line": chunk.get("end_line", 0),
                    "updated_at": datetime.now().isoformat()
                }

                self.vector_store.add_documents(
                    collection_name=collection_name,
                    documents=[chunk["content"]],
                    embeddings=[embedding],
                    metadatas=[metadata],
                    ids=[self._generate_chunk_id(rel_path, chunk)]
                )

                chunk_count += 1
            except Exception as e:
                logger.warning(f"向量化失败 {rel_path}: {e}")

        return {
            "path": rel_path,
            "size": file_size,
            "lines": content.count("\n") + 1,
            "symbols": symbols,
            "summary": summary,
            "chunks": chunk_count,
            "updated_at": datetime.fromtimestamp(
                path.stat().st_mtime
            ).isoformat()
        }

    def _generate_summary(
        self,
        content: str,
        symbols: list[SymbolInfo]
    ) -> str:
        """生成文件摘要"""
        lines = content.split("\n")

        summary_parts = []

        for _i, line in enumerate(lines[:20]):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("//"):
                summary_parts.append(stripped)

        for symbol in symbols[:10]:
            if symbol.type in ["class", "function", "component"]:
                params = ""
                if symbol.parameters:
                    params = f"({', '.join(symbol.parameters[:3])})"
                    if len(symbol.parameters) > 3:
                        params += ", ..."
                summary_parts.append(f"{symbol.type} {symbol.name}{params}")

        return "\n".join(summary_parts[:10])

    def _chunk_content(
        self,
        content: str,
        symbols: list[SymbolInfo]
    ) -> list[dict[str, Any]]:
        """
        将内容分块
        策略：
        - 小文件（< 2000 字符）：整个文件作为一个块
        - 大文件：按符号分块（每个类/函数一个块）
        """
        chunks = []
        lines = content.split("\n")

        if len(content) < 2000:
            chunks.append({
                "content": content,
                "symbol_type": "file",
                "symbol_name": "",
                "start_line": 1,
                "end_line": len(lines)
            })
            return chunks

        sorted_symbols = sorted(symbols, key=lambda s: s.line)

        for i, symbol in enumerate(sorted_symbols):
            start_line = symbol.line - 1
            end_line = len(lines)

            if i + 1 < len(sorted_symbols):
                next_symbol = sorted_symbols[i + 1]
                end_line = next_symbol.line - 1

            chunk_lines = lines[start_line:end_line]
            chunk_content = "\n".join(chunk_lines)

            if len(chunk_content) > self.config["max_content_length"]:
                chunk_content = chunk_content[:self.config["max_content_length"]]

            if chunk_content.strip():
                chunks.append({
                    "content": chunk_content,
                    "symbol_type": symbol.type,
                    "symbol_name": symbol.name,
                    "start_line": start_line + 1,
                    "end_line": start_line + len(chunk_lines)
                })

        if not chunks:
            chunk_size = 1000
            for i in range(0, len(content), chunk_size):
                chunk = content[i:i + chunk_size]
                if chunk.strip():
                    chunks.append({
                        "content": chunk,
                        "symbol_type": "chunk",
                        "symbol_name": f"part_{i // chunk_size}",
                        "start_line": content[:i].count("\n") + 1,
                        "end_line": content[:i + chunk_size].count("\n") + 1
                    })

        return chunks

    def _generate_chunk_id(self, rel_path: str, chunk: dict) -> str:
        """生成唯一 ID"""
        content = f"{rel_path}:{chunk.get('symbol_name', '')}:{chunk.get('start_line', 0)}"
        return f"chunk_{hashlib.md5(content.encode()).hexdigest()[:16]}"

    def _detect_language(self, path: Path) -> str:
        """检测文件语言"""
        ext = path.suffix.lower()

        lang_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".jsx": "javascript",
            ".tsx": "typescript",
            ".vue": "javascript",
            ".java": "java",
            ".go": "go",
            ".rs": "rust",
            ".rb": "ruby",
            ".php": "php",
        }

        return lang_map.get(ext, "unknown")

    def _should_ignore(self, path: Path) -> bool:
        """检查是否应该忽略该路径"""
        path_str = str(path)
        return any(pattern in path_str for pattern in self.config["ignore_patterns"])

    def get_index_info(self, collection_name: str) -> dict | None:
        """获取索引信息"""
        return self.index_cache.get(collection_name)

    def clear_cache(self):
        """清除缓存"""
        self.index_cache.clear()


_global_indices: dict[str, CodeIndexer] = {}


def get_code_indexer(
    embedder=None,
    vector_store=None,
    config: dict | None = None
) -> CodeIndexer:
    """获取代码索引器实例"""
    key = "default"
    if key not in _global_indices:
        _global_indices[key] = CodeIndexer(
            embedder=embedder,
            vector_store=vector_store,
            config=config
        )
    return _global_indices[key]
