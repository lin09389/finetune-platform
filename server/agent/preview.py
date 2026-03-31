"""
操作预览模块 - 执行前预览操作影响
"""
import logging
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ResourceInfo:
    type: str
    path: str
    size: int | None = None
    exists: bool = True
    is_directory: bool = False
    description: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PreviewResult:
    action: str
    description: str
    affected_resources: list[dict[str, Any]]
    estimated_duration: float
    risk_level: str
    warnings: list[str]
    suggestions: list[str]
    rollback_possible: bool
    rollback_operations: list[str]
    can_execute: bool
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class OperationPreviewer:
    HIGH_RISK_ACTIONS = {
        "file_delete",
        "directory_delete",
        "process_kill",
        "service_stop",
        "format_disk",
    }

    NON_ROLLBACK_ACTIONS = {
        "file_delete_permanent",
        "format_disk",
        "system_shutdown",
    }

    def __init__(self, working_dir: str = "."):
        self.working_dir = Path(working_dir).resolve()

    async def preview(
        self,
        action: str,
        params: dict[str, Any],
    ) -> PreviewResult:
        preview_method = getattr(self, f"_preview_{action}", self._preview_generic)
        return await preview_method(action, params)

    async def _preview_generic(
        self, action: str, params: dict[str, Any]
    ) -> PreviewResult:
        return PreviewResult(
            action=action,
            description=f"执行操作: {action}",
            affected_resources=[],
            estimated_duration=0.5,
            risk_level=RiskLevel.LOW.value,
            warnings=[],
            suggestions=[],
            rollback_possible=action not in self.NON_ROLLBACK_ACTIONS,
            rollback_operations=[],
            can_execute=True,
        )

    async def _preview_file_read(
        self, action: str, params: dict[str, Any]
    ) -> PreviewResult:
        file_path = params.get("file_path", "")
        path = self._resolve_path(file_path)

        warnings = []
        affected = []

        if not path.exists():
            return PreviewResult(
                action=action,
                description=f"读取文件: {file_path}",
                affected_resources=[],
                estimated_duration=0.1,
                risk_level=RiskLevel.LOW.value,
                warnings=["文件不存在"],
                suggestions=["请检查文件路径是否正确"],
                rollback_possible=True,
                rollback_operations=[],
                can_execute=False,
                error="文件不存在",
            )

        size = path.stat().st_size
        affected.append(ResourceInfo(
            type="file",
            path=str(path),
            size=size,
            exists=True,
            is_directory=False,
            description=f"文件大小: {self._format_size(size)}",
        ).to_dict())

        if size > 10 * 1024 * 1024:
            warnings.append(f"文件较大 ({self._format_size(size)})，读取可能需要一些时间")

        return PreviewResult(
            action=action,
            description=f"读取文件: {path.name}",
            affected_resources=affected,
            estimated_duration=min(size / (1024 * 1024), 5),
            risk_level=RiskLevel.LOW.value,
            warnings=warnings,
            suggestions=[],
            rollback_possible=True,
            rollback_operations=[],
            can_execute=True,
        )

    async def _preview_file_write(
        self, action: str, params: dict[str, Any]
    ) -> PreviewResult:
        file_path = params.get("file_path", "")
        content = params.get("content", "")
        path = self._resolve_path(file_path)

        warnings = []
        suggestions = []
        affected = []

        exists = path.exists()
        old_size = path.stat().st_size if exists else 0
        new_size = len(content.encode("utf-8"))

        affected.append(ResourceInfo(
            type="file",
            path=str(path),
            size=new_size,
            exists=exists,
            is_directory=False,
            description=f"{'覆盖' if exists else '创建'}文件，大小: {self._format_size(new_size)}",
        ).to_dict())

        if exists:
            warnings.append(f"文件已存在，将被覆盖（原大小: {self._format_size(old_size)}）")
            suggestions.append("建议先备份原文件")

        return PreviewResult(
            action=action,
            description=f"{'覆盖' if exists else '创建'}文件: {path.name}",
            affected_resources=affected,
            estimated_duration=0.2,
            risk_level=RiskLevel.MEDIUM.value if exists else RiskLevel.LOW.value,
            warnings=warnings,
            suggestions=suggestions,
            rollback_possible=True,
            rollback_operations=["恢复原文件内容"],
            can_execute=True,
        )

    async def _preview_file_delete(
        self, action: str, params: dict[str, Any]
    ) -> PreviewResult:
        file_path = params.get("file_path", "")
        path = self._resolve_path(file_path)

        warnings = []
        affected = []

        if not path.exists():
            return PreviewResult(
                action=action,
                description=f"删除文件: {file_path}",
                affected_resources=[],
                estimated_duration=0.1,
                risk_level=RiskLevel.LOW.value,
                warnings=["文件不存在，无需删除"],
                suggestions=[],
                rollback_possible=True,
                rollback_operations=[],
                can_execute=False,
                error="文件不存在",
            )

        size = path.stat().st_size
        affected.append(ResourceInfo(
            type="file",
            path=str(path),
            size=size,
            exists=True,
            is_directory=False,
            description=f"文件大小: {self._format_size(size)}",
        ).to_dict())

        warnings.append("删除后文件将无法恢复（除非有备份）")

        return PreviewResult(
            action=action,
            description=f"删除文件: {path.name}",
            affected_resources=affected,
            estimated_duration=0.1,
            risk_level=RiskLevel.HIGH.value,
            warnings=warnings,
            suggestions=["建议先创建备份"],
            rollback_possible=True,
            rollback_operations=["从备份恢复"],
            can_execute=True,
        )

    async def _preview_file_copy(
        self, action: str, params: dict[str, Any]
    ) -> PreviewResult:
        source = params.get("source", "")
        destination = params.get("destination", "")
        src_path = self._resolve_path(source)
        dest_path = self._resolve_path(destination)

        warnings = []
        affected = []

        if not src_path.exists():
            return PreviewResult(
                action=action,
                description=f"复制文件: {source}",
                affected_resources=[],
                estimated_duration=0.1,
                risk_level=RiskLevel.LOW.value,
                warnings=["源文件不存在"],
                suggestions=[],
                rollback_possible=True,
                rollback_operations=[],
                can_execute=False,
                error="源文件不存在",
            )

        src_size = src_path.stat().st_size if src_path.is_file() else 0

        affected.append(ResourceInfo(
            type="file",
            path=str(src_path),
            size=src_size,
            exists=True,
            is_directory=src_path.is_dir(),
            description="源文件",
        ).to_dict())

        affected.append(ResourceInfo(
            type="file",
            path=str(dest_path),
            size=src_size,
            exists=dest_path.exists(),
            is_directory=False,
            description="目标位置",
        ).to_dict())

        if dest_path.exists():
            warnings.append("目标位置已存在同名文件，将被覆盖")

        return PreviewResult(
            action=action,
            description=f"复制: {src_path.name} -> {dest_path}",
            affected_resources=affected,
            estimated_duration=src_size / (10 * 1024 * 1024),
            risk_level=RiskLevel.LOW.value,
            warnings=warnings,
            suggestions=[],
            rollback_possible=True,
            rollback_operations=["删除复制的文件"],
            can_execute=True,
        )

    async def _preview_file_move(
        self, action: str, params: dict[str, Any]
    ) -> PreviewResult:
        source = params.get("source", "")
        destination = params.get("destination", "")
        src_path = self._resolve_path(source)
        dest_path = self._resolve_path(destination)

        warnings = []
        affected = []

        if not src_path.exists():
            return PreviewResult(
                action=action,
                description=f"移动文件: {source}",
                affected_resources=[],
                estimated_duration=0.1,
                risk_level=RiskLevel.LOW.value,
                warnings=["源文件不存在"],
                suggestions=[],
                rollback_possible=True,
                rollback_operations=[],
                can_execute=False,
                error="源文件不存在",
            )

        src_size = src_path.stat().st_size if src_path.is_file() else 0

        affected.append(ResourceInfo(
            type="file",
            path=str(src_path),
            size=src_size,
            exists=True,
            is_directory=src_path.is_dir(),
            description="源位置",
        ).to_dict())

        affected.append(ResourceInfo(
            type="file",
            path=str(dest_path),
            size=src_size,
            exists=dest_path.exists(),
            is_directory=False,
            description="目标位置",
        ).to_dict())

        if dest_path.exists():
            warnings.append("目标位置已存在同名文件，将被覆盖")

        return PreviewResult(
            action=action,
            description=f"移动: {src_path.name} -> {dest_path}",
            affected_resources=affected,
            estimated_duration=0.2,
            risk_level=RiskLevel.MEDIUM.value,
            warnings=warnings,
            suggestions=[],
            rollback_possible=True,
            rollback_operations=["移动回原位置"],
            can_execute=True,
        )

    async def _preview_file_list(
        self, action: str, params: dict[str, Any]
    ) -> PreviewResult:
        directory = params.get("directory", ".")
        pattern = params.get("pattern", "*")
        recursive = params.get("recursive", False)
        path = self._resolve_path(directory)

        if not path.exists():
            return PreviewResult(
                action=action,
                description=f"列出目录: {directory}",
                affected_resources=[],
                estimated_duration=0.1,
                risk_level=RiskLevel.LOW.value,
                warnings=["目录不存在"],
                suggestions=[],
                rollback_possible=True,
                rollback_operations=[],
                can_execute=False,
                error="目录不存在",
            )

        try:
            if recursive:
                items = list(path.rglob(pattern))
            else:
                items = list(path.glob(pattern))

            affected = []
            total_size = 0

            for item in items[:20]:
                try:
                    size = item.stat().st_size if item.is_file() else 0
                    total_size += size
                    affected.append(ResourceInfo(
                        type="file" if item.is_file() else "directory",
                        path=str(item),
                        size=size if item.is_file() else None,
                        exists=True,
                        is_directory=item.is_dir(),
                    ).to_dict())
                except Exception:
                    continue

            return PreviewResult(
                action=action,
                description=f"列出目录: {path.name}（{len(items)} 个项目）",
                affected_resources=affected,
                estimated_duration=0.5,
                risk_level=RiskLevel.LOW.value,
                warnings=[],
                suggestions=[],
                rollback_possible=True,
                rollback_operations=[],
                can_execute=True,
            )

        except Exception as e:
            return PreviewResult(
                action=action,
                description=f"列出目录: {directory}",
                affected_resources=[],
                estimated_duration=0.1,
                risk_level=RiskLevel.LOW.value,
                warnings=[f"读取目录失败: {e}"],
                suggestions=[],
                rollback_possible=True,
                rollback_operations=[],
                can_execute=False,
                error=str(e),
            )

    async def _preview_directory_delete(
        self, action: str, params: dict[str, Any]
    ) -> PreviewResult:
        directory = params.get("directory", "")
        recursive = params.get("recursive", False)
        path = self._resolve_path(directory)

        warnings = []
        affected = []

        if not path.exists():
            return PreviewResult(
                action=action,
                description=f"删除目录: {directory}",
                affected_resources=[],
                estimated_duration=0.1,
                risk_level=RiskLevel.LOW.value,
                warnings=["目录不存在"],
                suggestions=[],
                rollback_possible=True,
                rollback_operations=[],
                can_execute=False,
                error="目录不存在",
            )

        if not path.is_dir():
            return PreviewResult(
                action=action,
                description=f"删除目录: {directory}",
                affected_resources=[],
                estimated_duration=0.1,
                risk_level=RiskLevel.LOW.value,
                warnings=["路径不是目录"],
                suggestions=[],
                rollback_possible=True,
                rollback_operations=[],
                can_execute=False,
                error="路径不是目录",
            )

        try:
            items = list(path.iterdir())
            total_size = sum(
                f.stat().st_size for f in path.rglob("*") if f.is_file()
            )

            affected.append(ResourceInfo(
                type="directory",
                path=str(path),
                size=total_size,
                exists=True,
                is_directory=True,
                description=f"包含 {len(items)} 个项目，总大小: {self._format_size(total_size)}",
            ).to_dict())

            if items and not recursive:
                warnings.append("目录不为空，需要设置 recursive=true 才能删除")

            if items:
                warnings.append(f"将删除 {len(items)} 个项目，共 {self._format_size(total_size)}")

        except Exception as e:
            warnings.append(f"无法读取目录内容: {e}")

        return PreviewResult(
            action=action,
            description=f"删除目录: {path.name}",
            affected_resources=affected,
            estimated_duration=1.0,
            risk_level=RiskLevel.CRITICAL.value,
            warnings=warnings,
            suggestions=["删除前请确认目录内容", "建议先备份重要文件"],
            rollback_possible=True,
            rollback_operations=["从备份恢复目录"],
            can_execute=True,
        )

    async def _preview_process_list(
        self, action: str, params: dict[str, Any]
    ) -> PreviewResult:
        return PreviewResult(
            action=action,
            description="列出所有进程",
            affected_resources=[],
            estimated_duration=0.5,
            risk_level=RiskLevel.LOW.value,
            warnings=[],
            suggestions=[],
            rollback_possible=True,
            rollback_operations=[],
            can_execute=True,
        )

    async def _preview_app_open(
        self, action: str, params: dict[str, Any]
    ) -> PreviewResult:
        app_name = params.get("app_name", "")

        return PreviewResult(
            action=action,
            description=f"打开应用: {app_name}",
            affected_resources=[ResourceInfo(
                type="application",
                path=app_name,
                exists=True,
                is_directory=False,
                description="应用程序",
            ).to_dict()],
            estimated_duration=1.0,
            risk_level=RiskLevel.LOW.value,
            warnings=[],
            suggestions=[],
            rollback_possible=True,
            rollback_operations=["关闭应用"],
            can_execute=True,
        )

    def _resolve_path(self, path: str) -> Path:
        p = Path(path)
        if not p.is_absolute():
            p = self.working_dir / p
        return p.resolve()

    def _format_size(self, size: int) -> str:
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"


_previewer: OperationPreviewer | None = None


def get_previewer() -> OperationPreviewer:
    global _previewer
    if _previewer is None:
        _previewer = OperationPreviewer()
    return _previewer
