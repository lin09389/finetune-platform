import asyncio
import fnmatch
import re
from pathlib import Path
from typing import Optional, Callable, Awaitable, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime, timedelta


class SearchCriteria(BaseModel):
    name_pattern: Optional[str] = None
    content_pattern: Optional[str] = None
    min_size: Optional[int] = None
    max_size: Optional[int] = None
    modified_after: Optional[str] = None
    modified_before: Optional[str] = None
    extensions: Optional[List[str]] = None
    is_file: Optional[bool] = None
    is_dir: Optional[bool] = None
    use_regex: bool = False
    case_sensitive: bool = False


class SearchResult(BaseModel):
    path: str
    name: str
    is_dir: bool = False
    size: int = 0
    modified: str = ""
    match_type: str = "name"
    line_number: Optional[int] = None
    line_content: Optional[str] = None


class SearchResults(BaseModel):
    success: bool = Field(default=True)
    criteria: SearchCriteria
    results: List[SearchResult] = Field(default_factory=list)
    total: int = 0
    scanned: int = 0
    error: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class FileSearchExecutor:
    def __init__(
        self,
        progress_callback: Optional[Callable[[str, float, str], Awaitable[None]]] = None,
        max_results: int = 1000,
    ):
        self.progress_callback = progress_callback
        self.max_results = max_results

    async def search(
        self,
        directory: str,
        criteria: SearchCriteria,
        recursive: bool = True,
    ) -> SearchResults:
        dir_path = Path(directory)

        if not dir_path.exists():
            return SearchResults(
                success=False,
                criteria=criteria,
                error=f"目录不存在: {directory}",
            )

        if not dir_path.is_dir():
            return SearchResults(
                success=False,
                criteria=criteria,
                error=f"路径不是目录: {directory}",
            )

        try:
            results: List[SearchResult] = []
            scanned = 0

            if recursive:
                items = list(dir_path.rglob("*"))
            else:
                items = list(dir_path.iterdir())

            total = len(items)

            for idx, item in enumerate(items):
                if len(results) >= self.max_results:
                    break

                scanned += 1

                if self.progress_callback and idx % 100 == 0:
                    progress = idx / total if total > 0 else 0.0
                    await self.progress_callback(
                        directory,
                        progress,
                        f"搜索进度: {scanned} 个项目",
                    )

                if not self._matches_criteria(item, criteria):
                    continue

                if criteria.content_pattern and item.is_file():
                    content_results = await self._search_content(item, criteria)
                    results.extend(content_results)
                else:
                    try:
                        stat = item.stat()
                        result = SearchResult(
                            path=str(item),
                            name=item.name,
                            is_dir=item.is_dir(),
                            size=stat.st_size if item.is_file() else 0,
                            modified=datetime.fromtimestamp(stat.st_mtime).isoformat(),
                            match_type="name",
                        )
                        results.append(result)
                    except Exception:
                        continue

            return SearchResults(
                success=True,
                criteria=criteria,
                results=results,
                total=len(results),
                scanned=scanned,
            )

        except Exception as e:
            return SearchResults(
                success=False,
                criteria=criteria,
                error=f"搜索失败: {str(e)}",
            )

    async def search_by_name(
        self,
        directory: str,
        pattern: str,
        recursive: bool = True,
        use_regex: bool = False,
        case_sensitive: bool = False,
    ) -> SearchResults:
        criteria = SearchCriteria(
            name_pattern=pattern,
            use_regex=use_regex,
            case_sensitive=case_sensitive,
        )
        return await self.search(directory, criteria, recursive)

    async def search_by_content(
        self,
        directory: str,
        pattern: str,
        recursive: bool = True,
        use_regex: bool = False,
        case_sensitive: bool = False,
        extensions: Optional[List[str]] = None,
    ) -> SearchResults:
        criteria = SearchCriteria(
            content_pattern=pattern,
            use_regex=use_regex,
            case_sensitive=case_sensitive,
            extensions=extensions,
            is_file=True,
        )
        return await self.search(directory, criteria, recursive)

    async def search_by_size(
        self,
        directory: str,
        min_size: Optional[int] = None,
        max_size: Optional[int] = None,
        recursive: bool = True,
    ) -> SearchResults:
        criteria = SearchCriteria(
            min_size=min_size,
            max_size=max_size,
            is_file=True,
        )
        return await self.search(directory, criteria, recursive)

    async def search_by_time(
        self,
        directory: str,
        modified_after: Optional[str] = None,
        modified_before: Optional[str] = None,
        recursive: bool = True,
    ) -> SearchResults:
        criteria = SearchCriteria(
            modified_after=modified_after,
            modified_before=modified_before,
        )
        return await self.search(directory, criteria, recursive)

    async def search_by_extension(
        self,
        directory: str,
        extensions: List[str],
        recursive: bool = True,
    ) -> SearchResults:
        normalized_extensions = []
        for ext in extensions:
            if not ext.startswith("."):
                ext = "." + ext
            normalized_extensions.append(ext.lower())

        criteria = SearchCriteria(
            extensions=normalized_extensions,
            is_file=True,
        )
        return await self.search(directory, criteria, recursive)

    async def find_duplicates(
        self,
        directory: str,
        recursive: bool = True,
    ) -> Dict[str, List[str]]:
        dir_path = Path(directory)

        if not dir_path.exists() or not dir_path.is_dir():
            return {}

        try:
            size_map: Dict[int, List[str]] = {}

            if recursive:
                items = list(dir_path.rglob("*"))
            else:
                items = list(dir_path.iterdir())

            files = [f for f in items if f.is_file()]

            if self.progress_callback:
                await self.progress_callback(
                    directory,
                    0.0,
                    f"开始查找重复文件: {len(files)} 个文件",
                )

            for idx, file_path in enumerate(files):
                try:
                    size = file_path.stat().st_size
                    if size not in size_map:
                        size_map[size] = []
                    size_map[size].append(str(file_path))
                except Exception:
                    continue

                if self.progress_callback and idx % 100 == 0:
                    progress = idx / len(files) if files else 0.0
                    await self.progress_callback(
                        directory,
                        progress,
                        f"查找进度: {idx + 1}/{len(files)}",
                    )

            duplicates: Dict[str, List[str]] = {}
            for size, paths in size_map.items():
                if len(paths) > 1:
                    duplicates[f"size_{size}"] = paths

            if self.progress_callback:
                await self.progress_callback(
                    directory,
                    1.0,
                    f"查找完成: 发现 {len(duplicates)} 组重复文件",
                )

            return duplicates

        except Exception:
            return {}

    async def find_empty_directories(
        self,
        directory: str,
        recursive: bool = True,
    ) -> List[str]:
        dir_path = Path(directory)

        if not dir_path.exists() or not dir_path.is_dir():
            return []

        try:
            empty_dirs = []

            if recursive:
                dirs = [d for d in dir_path.rglob("*") if d.is_dir()]
            else:
                dirs = [d for d in dir_path.iterdir() if d.is_dir()]

            for dir_item in dirs:
                try:
                    if not any(dir_item.iterdir()):
                        empty_dirs.append(str(dir_item))
                except Exception:
                    continue

            return empty_dirs

        except Exception:
            return []

    def _matches_criteria(self, item: Path, criteria: SearchCriteria) -> bool:
        try:
            if criteria.is_file is not None:
                if criteria.is_file and not item.is_file():
                    return False
                if not criteria.is_file and not item.is_dir():
                    return False

            if criteria.is_dir is not None:
                if criteria.is_dir and not item.is_dir():
                    return False
                if not criteria.is_dir and not item.is_file():
                    return False

            if criteria.name_pattern:
                name = item.name
                pattern = criteria.name_pattern

                if not criteria.case_sensitive:
                    name = name.lower()
                    pattern = pattern.lower()

                if criteria.use_regex:
                    if not re.search(pattern, name):
                        return False
                else:
                    if not fnmatch.fnmatch(name, pattern):
                        return False

            if criteria.extensions and item.is_file():
                ext = item.suffix.lower()
                if ext not in [e.lower() for e in criteria.extensions]:
                    return False

            if item.is_file():
                stat = item.stat()

                if criteria.min_size is not None:
                    if stat.st_size < criteria.min_size:
                        return False

                if criteria.max_size is not None:
                    if stat.st_size > criteria.max_size:
                        return False

                if criteria.modified_after or criteria.modified_before:
                    mtime = datetime.fromtimestamp(stat.st_mtime)

                    if criteria.modified_after:
                        try:
                            after_date = datetime.fromisoformat(criteria.modified_after)
                            if mtime < after_date:
                                return False
                        except ValueError:
                            pass

                    if criteria.modified_before:
                        try:
                            before_date = datetime.fromisoformat(criteria.modified_before)
                            if mtime > before_date:
                                return False
                        except ValueError:
                            pass

            return True

        except Exception:
            return False

    async def _search_content(
        self,
        file_path: Path,
        criteria: SearchCriteria,
    ) -> List[SearchResult]:
        results: List[SearchResult] = []

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()

            pattern = criteria.content_pattern
            if not pattern:
                return results

            flags = 0
            if not criteria.case_sensitive:
                flags |= re.IGNORECASE

            if criteria.use_regex:
                regex = re.compile(pattern, flags)
            else:
                escaped = re.escape(pattern)
                regex = re.compile(escaped, flags)

            stat = file_path.stat()

            for line_num, line in enumerate(lines, 1):
                match = regex.search(line)
                if match:
                    result = SearchResult(
                        path=str(file_path),
                        name=file_path.name,
                        is_dir=False,
                        size=stat.st_size,
                        modified=datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        match_type="content",
                        line_number=line_num,
                        line_content=line.strip()[:200],
                    )
                    results.append(result)

                    if len(results) >= self.max_results:
                        break

        except Exception:
            pass

        return results
