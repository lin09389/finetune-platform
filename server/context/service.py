"""
项目上下文服务
封装项目扫描、索引、检索、@ mention 和轻量依赖拓扑扩展。
"""
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .code_indexer import CodeIndexer as RichCodeIndexer
from .models import ContextResult, FileInfo, ProjectInfo
from .project_scanner import ProjectScanner
from .symbol_extractor import get_symbol_extractor

logger = logging.getLogger(__name__)


class CodeIndexer:
    """代码索引器（简化版）"""

    def __init__(self, embedder=None, vector_store=None):
        self.embedder = embedder
        self.vector_store = vector_store
        self._indexed_files: dict[str, list[str]] = {}

    def index_project(self, project_info: ProjectInfo, force_reindex: bool = False) -> dict[str, Any]:
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

    def get_stats(self, project_path: str) -> dict[str, Any]:
        """获取索引统计"""
        return {
            "indexed_files": len(self._indexed_files.get(project_path, []))
        }


class ContextService:
    """项目上下文服务"""

    def __init__(self, embedder=None, vector_store=None):
        self.projects: dict[str, ProjectInfo] = {}
        self.scanner = ProjectScanner()
        self.indexer = CodeIndexer(embedder=embedder, vector_store=vector_store)
        self.code_indexer = RichCodeIndexer(embedder=embedder, vector_store=vector_store)
        self.symbol_extractor = get_symbol_extractor()
        self.retriever = None
        self.project_indexes: dict[str, dict[str, Any]] = {}

    def scan_project(self, project_path: str) -> ProjectInfo:
        """扫描项目"""
        project_info = self.scanner.scan(project_path)
        self.projects[project_path] = project_info
        return project_info

    def index_project(
        self,
        project_path: str,
        force_reindex: bool = False
    ) -> dict[str, Any]:
        """索引项目"""
        project_path = str(Path(project_path).expanduser().resolve())
        if project_path not in self.projects or force_reindex:
            self.scan_project(project_path)

        project_info = self.projects[project_path]
        indexed = self._build_lightweight_index(project_info)
        legacy = self.indexer.index_project(project_info, force_reindex)
        return {**legacy, **indexed}

    def retrieve(
        self,
        query: str,
        project_path: str | None = None,
        top_k: int = 5
    ) -> list[ContextResult]:
        """检索上下文"""
        if self.retriever:
            return self.retriever.retrieve(query, top_k)

        results = []
        normalized_project_path = str(Path(project_path).expanduser().resolve()) if project_path else None
        if normalized_project_path and normalized_project_path not in self.project_indexes:
            self.index_project(normalized_project_path)
        index = self.project_indexes.get(normalized_project_path or "")
        if index:
            mentions = self.search_mentions(query=query, project_path=normalized_project_path, limit=top_k)
            for item in mentions:
                results.append(ContextResult(
                    type=item["type"],
                    path=item.get("path"),
                    source_file=Path(str(item.get("path") or "")).name or item.get("label"),
                    relevance=float(item.get("score") or 0),
                    score=float(item.get("score") or 0),
                    content=item.get("content") or item.get("detail") or "",
                    symbols=[],
                ))
            return results

        if normalized_project_path and normalized_project_path in self.projects:
            project_info = self.projects[normalized_project_path]
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

    def search_mentions(
        self,
        query: str,
        project_path: str | None = None,
        kinds: list[str] | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """返回 @ mention 候选：文件、符号和 API endpoint。"""
        project_path = self._resolve_project_path(project_path)
        if not project_path:
            return []
        if project_path not in self.project_indexes:
            self.index_project(project_path)
        index = self.project_indexes.get(project_path, {})
        allowed = set(kinds or ["file", "symbol", "endpoint"])
        q = query.strip()
        candidates: list[dict[str, Any]] = []
        if "file" in allowed:
            for rel_path, file_data in (index.get("files") or {}).items():
                score = self._score_mention(q, rel_path, Path(rel_path).name)
                if score is None:
                    continue
                candidates.append({
                    "id": f"file:{rel_path}",
                    "type": "file",
                    "label": Path(rel_path).name,
                    "path": rel_path,
                    "detail": rel_path,
                    "score": score,
                    "source": "index",
                    "content": file_data.get("summary") or file_data.get("content_preview") or "",
                })
        if "symbol" in allowed:
            for symbol in index.get("symbols") or []:
                label = str(symbol.get("name") or "")
                score = self._score_mention(q, label, str(symbol.get("file_path") or ""))
                if score is None:
                    continue
                path = symbol.get("file_path")
                candidates.append({
                    "id": f"symbol:{path}:{label}:{symbol.get('line')}",
                    "type": "symbol",
                    "label": label,
                    "path": path,
                    "line": symbol.get("line"),
                    "detail": f"{symbol.get('type')} · {path}",
                    "score": score + 0.08,
                    "source": "index",
                    "content": symbol.get("docstring") or "",
                })
        if "endpoint" in allowed:
            for endpoint in index.get("endpoints") or []:
                label = str(endpoint.get("label") or endpoint.get("route") or "")
                score = self._score_mention(q, label, str(endpoint.get("path") or ""))
                if score is None:
                    continue
                candidates.append({
                    **endpoint,
                    "id": f"endpoint:{endpoint.get('method')}:{endpoint.get('route')}:{endpoint.get('path')}:{endpoint.get('line')}",
                    "type": "endpoint",
                    "score": score + 0.12,
                    "source": "index",
                })
        candidates.sort(key=lambda item: float(item.get("score") or 0), reverse=True)
        return candidates[: max(1, min(limit, 50))]

    def refresh_file(self, project_path: str | None, file_path: str) -> dict[str, Any]:
        """文件保存或 patch 后增量刷新单文件索引。"""
        raw_file = Path(file_path).expanduser()
        initial_project = str(Path(project_path).expanduser().resolve()) if project_path else None
        resolved_file = (
            (Path(initial_project) / raw_file).resolve()
            if initial_project and not raw_file.is_absolute()
            else raw_file.resolve()
        )
        resolved_project = self._resolve_project_path(initial_project, file_path=resolved_file)
        if not resolved_project:
            return {"refreshed": False, "reason": "project_not_found"}
        project_root = Path(resolved_project)
        if resolved_project not in self.project_indexes:
            self.index_project(resolved_project)
        try:
            rel_path = resolved_file.relative_to(project_root).as_posix()
        except ValueError:
            return {"refreshed": False, "reason": "outside_project"}
        index = self.project_indexes.setdefault(resolved_project, self._empty_index(resolved_project))
        if not resolved_file.exists() or resolved_file.is_dir():
            index.get("files", {}).pop(rel_path, None)
            index["symbols"] = [s for s in index.get("symbols", []) if s.get("file_path") != rel_path]
            index["endpoints"] = [e for e in index.get("endpoints", []) if e.get("path") != rel_path]
            self._rebuild_dependency_graph(resolved_project)
            return {"refreshed": True, "path": rel_path, "removed": True}
        file_data = self._index_one_file(project_root, resolved_file)
        if not file_data:
            return {"refreshed": False, "path": rel_path, "reason": "unsupported_or_empty"}
        index["files"][rel_path] = file_data
        index["symbols"] = [s for s in index.get("symbols", []) if s.get("file_path") != rel_path]
        index["symbols"].extend(symbol.model_dump() for symbol in file_data.get("symbols", []))
        index["endpoints"] = [e for e in index.get("endpoints", []) if e.get("path") != rel_path]
        index["endpoints"].extend(file_data.get("endpoints", []))
        index["updated_at"] = datetime.now().isoformat()
        self._rebuild_dependency_graph(resolved_project)
        self._sync_project_files(resolved_project)
        return {"refreshed": True, "path": rel_path, "symbols": len(file_data.get("symbols", []))}

    def refresh_changed_files(self, project_path: str | None, changed_files: list[str]) -> dict[str, Any]:
        refreshed = []
        for path in changed_files:
            result = self.refresh_file(project_path, path)
            if result.get("refreshed"):
                refreshed.append(result.get("path") or path)
        return {"refreshed_files": refreshed, "count": len(refreshed)}

    def expand_deep_context(
        self,
        active_context: dict[str, Any] | None,
        explicit_context: list[dict[str, Any]] | None,
        project_path: str | None = None,
        max_items: int = 6,
    ) -> list[dict[str, Any]]:
        """基于 active/@ context 扩展一圈 import/reverse import/符号引用依赖。"""
        resolved_project = self._resolve_project_path(project_path, file_path=active_context.get("file_path") if isinstance(active_context, dict) else None)
        if not resolved_project:
            return []
        if resolved_project not in self.project_indexes:
            self.index_project(resolved_project)
        index = self.project_indexes.get(resolved_project, {})
        graph = index.get("dependency_graph") or {}
        seed_paths = self._extract_seed_paths(resolved_project, active_context, explicit_context)
        seed_symbols = [
            str(item.get("label"))
            for item in explicit_context or []
            if isinstance(item, dict) and item.get("type") == "symbol" and item.get("label")
        ]
        related: list[dict[str, Any]] = []
        seen: set[str] = set(seed_paths)
        for path in seed_paths:
            for relation, rel_paths in (
                ("imports", (graph.get("imports") or {}).get(path, [])),
                ("imported_by", (graph.get("reverse_imports") or {}).get(path, [])),
            ):
                for rel_path in rel_paths:
                    if rel_path in seen:
                        continue
                    file_data = (index.get("files") or {}).get(rel_path)
                    if not file_data:
                        continue
                    seen.add(rel_path)
                    related.append({
                        "type": "file",
                        "relation": relation,
                        "path": rel_path,
                        "label": Path(rel_path).name,
                        "content": file_data.get("summary") or file_data.get("content_preview") or "",
                    })
                    if len(related) >= max_items:
                        return related
        for symbol in seed_symbols:
            for ref in (graph.get("symbol_references") or {}).get(symbol, []):
                rel_path = ref.get("path")
                key = f"{symbol}:{rel_path}:{ref.get('line')}"
                if not rel_path or key in seen:
                    continue
                seen.add(key)
                related.append({
                    "type": "symbol_reference",
                    "relation": "references",
                    "label": symbol,
                    "path": rel_path,
                    "line": ref.get("line"),
                    "content": ref.get("line_text") or "",
                })
                if len(related) >= max_items:
                    return related
        return related

    def get_context_for_chat(
        self,
        query: str,
        project_path: str | None = None,
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

    def list_projects(self) -> list[dict[str, Any]]:
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
            self.project_indexes.pop(project_path, None)
            return True
        return False

    def get_project_stats(self, project_path: str) -> dict[str, Any] | None:
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
            "index_stats": {
                **index_stats,
                **(self.project_indexes.get(project_path, {}).get("summary") or {}),
            },
        }

    def _build_lightweight_index(self, project_info: ProjectInfo) -> dict[str, Any]:
        project_root = Path(project_info.path).expanduser().resolve()
        index = self._empty_index(str(project_root))
        for file_path in self._iter_code_files(project_root):
            file_data = self._index_one_file(project_root, file_path)
            if not file_data:
                continue
            rel_path = file_data["path"]
            index["files"][rel_path] = file_data
            index["symbols"].extend(symbol.model_dump() for symbol in file_data.get("symbols", []))
            index["endpoints"].extend(file_data.get("endpoints", []))
        index["summary"] = {
            "files_indexed": len(index["files"]),
            "symbols_indexed": len(index["symbols"]),
            "endpoints_indexed": len(index["endpoints"]),
            "indexed_at": index["updated_at"],
        }
        self.project_indexes[str(project_root)] = index
        self._rebuild_dependency_graph(str(project_root))
        self._sync_project_files(str(project_root))
        try:
            self._persist_lightweight_index(str(project_root))
        except Exception as exc:
            logger.debug("lightweight index persist failed: %s", exc)
        return index["summary"]

    def _lightweight_index_path(self, project_path: str) -> Path:
        """Return the on-disk path used to persist a project's lightweight index."""
        try:
            from core.config import get_settings

            base = Path(get_settings().base_dir) / "context_cache"
        except Exception:
            base = Path.cwd() / "context_cache"
        import hashlib

        digest = hashlib.sha1(str(Path(project_path).resolve()).encode("utf-8")).hexdigest()[:16]
        return base / f"project_{digest}.lightweight.json"

    def _persist_lightweight_index(self, project_path: str) -> None:
        """Write a project's lightweight index to disk so later sessions can reload it."""
        index = self.project_indexes.get(project_path)
        if index is None:
            return
        path = self._lightweight_index_path(project_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        import json

        payload = json.dumps(index, ensure_ascii=False)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(path)

    def _load_lightweight_index(self, project_path: str) -> bool:
        """Reload a persisted lightweight index for a project.

        Returns True when an index was loaded into ``self.project_indexes``.
        """
        path = self._lightweight_index_path(project_path)
        if not path.exists():
            return False
        try:
            import json

            index = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.debug("lightweight index load failed: %s", exc)
            return False
        if not isinstance(index, dict):
            return False
        self.project_indexes[project_path] = index
        return True

    def _empty_index(self, project_path: str) -> dict[str, Any]:
        return {
            "project_path": project_path,
            "files": {},
            "symbols": [],
            "endpoints": [],
            "dependency_graph": {"imports": {}, "reverse_imports": {}, "symbol_references": {}},
            "updated_at": datetime.now().isoformat(),
            "summary": {},
        }

    def _iter_code_files(self, project_root: Path):
        for ext in self.code_indexer.config["supported_extensions"]:
            try:
                candidates = project_root.glob(f"**/*{ext}")
                for file_path in candidates:
                    if not self.code_indexer._should_ignore(file_path):
                        yield file_path
            except OSError as exc:
                logger.warning("跳过不可访问的项目路径：%s", exc)

    def _index_one_file(self, project_root: Path, file_path: Path) -> dict[str, Any] | None:
        try:
            if file_path.stat().st_size > self.code_indexer.config["max_file_size"]:
                return None
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return None
        if not content.strip():
            return None
        rel_path = file_path.relative_to(project_root).as_posix()
        symbols = self.symbol_extractor.extract(str(file_path), content)
        for symbol in symbols:
            symbol.file_path = rel_path
        return {
            "path": rel_path,
            "name": file_path.name,
            "size": file_path.stat().st_size,
            "lines": content.count("\n") + 1,
            "language": self.code_indexer._detect_language(file_path),
            "symbols": symbols,
            "summary": self.code_indexer._generate_summary(content, symbols),
            "content_preview": content[:2000],
            "imports": self._extract_imports(content, rel_path),
            "endpoints": self._extract_endpoints(content, rel_path),
            "updated_at": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat(),
        }

    def _extract_imports(self, content: str, rel_path: str) -> list[str]:
        imports: list[str] = []
        for pattern in [
            r"^\s*import\s+.*?\s+from\s+['\"](.+?)['\"]",
            r"^\s*import\s+['\"](.+?)['\"]",
            r"^\s*from\s+([\w.]+)\s+import\s+",
        ]:
            for match in re.finditer(pattern, content, re.MULTILINE):
                imports.append(str(match.group(1)))
        return imports[:80]

    def _extract_endpoints(self, content: str, rel_path: str) -> list[dict[str, Any]]:
        endpoints: list[dict[str, Any]] = []
        patterns = []
        if rel_path.endswith(".py"):
            patterns.append(re.compile(r"@(?:router|app)\.(get|post|put|patch|delete)\(\s*['\"]([^'\"]+)['\"]", re.MULTILINE))
        elif Path(rel_path).suffix.lower() in {".js", ".jsx", ".ts", ".tsx"}:
            patterns.append(re.compile(r"\b(?:app|router)\.(get|post|put|patch|delete)\(\s*['\"]([^'\"]+)['\"]", re.MULTILINE))
        seen: set[tuple[str, str, int]] = set()
        for pattern in patterns:
            for match in pattern.finditer(content):
                line = content[:match.start()].count("\n") + 1
                method = match.group(1).upper()
                route = match.group(2)
                key = (method, route, line)
                if key in seen:
                    continue
                seen.add(key)
                endpoints.append({
                    "type": "endpoint",
                    "label": f"{method} {route}",
                    "method": method,
                    "route": route,
                    "path": rel_path,
                    "line": line,
                    "detail": f"{method} {route} · {rel_path}",
                    "content": self._line_excerpt(content, line),
                })
        return endpoints

    def _rebuild_dependency_graph(self, project_path: str) -> None:
        index = self.project_indexes.get(project_path)
        if not index:
            return
        files = index.get("files") or {}
        imports: dict[str, list[str]] = {}
        reverse: dict[str, list[str]] = {}
        for rel_path, file_data in files.items():
            resolved = [
                dep for dep in (
                    self._resolve_import_to_path(rel_path, raw, files)
                    for raw in file_data.get("imports") or []
                )
                if dep
            ]
            imports[rel_path] = list(dict.fromkeys(resolved))
            for dep in imports[rel_path]:
                reverse.setdefault(dep, []).append(rel_path)
        symbol_refs: dict[str, list[dict[str, Any]]] = {}
        symbol_names = [str(s.get("name")) for s in index.get("symbols") or [] if s.get("name")]
        for rel_path, file_data in files.items():
            content = str(file_data.get("content_preview") or "")
            lines = content.splitlines()
            for symbol in symbol_names[:500]:
                pattern = re.compile(rf"(?<![\w$]){re.escape(symbol)}(?![\w$])")
                for idx, line in enumerate(lines, start=1):
                    if pattern.search(line):
                        symbol_refs.setdefault(symbol, []).append({
                            "path": rel_path,
                            "line": idx,
                            "line_text": line.strip()[:240],
                        })
                        break
        index["dependency_graph"] = {
            "imports": imports,
            "reverse_imports": reverse,
            "symbol_references": symbol_refs,
        }

    def _resolve_import_to_path(self, from_path: str, raw: str, files: dict[str, Any]) -> str | None:
        if not raw:
            return None
        candidates: list[str] = []
        if raw.startswith("."):
            base = Path(from_path).parent
            normalized = (base / raw).as_posix()
            candidates.extend([normalized, *[f"{normalized}{ext}" for ext in [".ts", ".tsx", ".js", ".jsx", ".py"]]])
            candidates.extend([f"{normalized}/index{ext}" for ext in [".ts", ".tsx", ".js", ".jsx"]])
        else:
            normalized = raw.replace(".", "/")
            candidates.extend([normalized, *[f"{normalized}{ext}" for ext in [".py", ".ts", ".tsx", ".js", ".jsx"]]])
        for candidate in candidates:
            clean = candidate.replace("\\", "/").lstrip("/")
            if clean in files:
                return clean
        return None

    def _extract_seed_paths(
        self,
        project_path: str,
        active_context: dict[str, Any] | None,
        explicit_context: list[dict[str, Any]] | None,
    ) -> list[str]:
        root = Path(project_path)
        seeds: list[str] = []
        for raw in [active_context.get("file_path") if isinstance(active_context, dict) else None]:
            rel = self._to_relative_path(root, raw)
            if rel:
                seeds.append(rel)
        for item in explicit_context or []:
            if isinstance(item, dict):
                rel = self._to_relative_path(root, item.get("path"))
                if rel:
                    seeds.append(rel)
        return list(dict.fromkeys(seeds))

    def _to_relative_path(self, root: Path, raw: Any) -> str | None:
        if not raw:
            return None
        value = str(raw).replace("\\", "/")
        try:
            path = Path(value)
            if path.is_absolute():
                return path.resolve().relative_to(root).as_posix()
        except Exception:
            pass
        return value.lstrip("/") if value else None

    def _resolve_project_path(self, project_path: str | None, file_path: Any | None = None) -> str | None:
        if project_path:
            return str(Path(project_path).expanduser().resolve())
        if file_path:
            path = Path(str(file_path)).expanduser().resolve()
            for known in self.projects.keys() | self.project_indexes.keys():
                try:
                    path.relative_to(Path(known))
                    return known
                except ValueError:
                    continue
        if self.projects:
            return next(iter(self.projects.keys()))
        if self.project_indexes:
            return next(iter(self.project_indexes.keys()))
        return None

    def _score_mention(self, query: str, label: str, detail: str = "") -> float | None:
        if not query:
            return 0.25
        q = query.lower()
        target = f"{label} {detail}".lower()
        if q in label.lower():
            return 1.0 - min(label.lower().index(q), 20) / 100
        if q in target:
            return 0.75
        pos = 0
        score = 0.0
        for char in q:
            found = target.find(char, pos)
            if found < 0:
                return None
            score += 1.0 / (1 + max(0, found - pos))
            pos = found + 1
        return min(0.7, score / max(1, len(q)))

    def _line_excerpt(self, content: str, line: int, radius: int = 2) -> str:
        lines = content.splitlines()
        start = max(0, line - radius - 1)
        end = min(len(lines), line + radius)
        return "\n".join(lines[start:end])[:1200]

    def _sync_project_files(self, project_path: str) -> None:
        project = self.projects.get(project_path)
        index = self.project_indexes.get(project_path)
        if not project or not index:
            return
        files = []
        for rel_path, data in (index.get("files") or {}).items():
            files.append(FileInfo(
                path=rel_path,
                name=data.get("name") or Path(rel_path).name,
                size=int(data.get("size") or 0),
                line_count=int(data.get("lines") or 0),
                language=data.get("language") or "text",
                symbols=data.get("symbols") or [],
                summary=data.get("summary"),
                updated_at=data.get("updated_at"),
            ))
        project.files = files


_service_instance: ContextService | None = None


def close_context_service() -> None:
    """Clear the process-wide context service singleton on application shutdown."""
    global _service_instance
    service = _service_instance
    _service_instance = None
    if service is None:
        return
    close = getattr(service, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            pass


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
    if _service_instance is not None:
        close_context_service()
    _service_instance = ContextService(
        embedder=embedder,
        vector_store=vector_store
    )
    return _service_instance
