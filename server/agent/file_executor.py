"""
文件操作执行器
支持创建、读取、写入、删除文件
所有操作都会进行安全路径检查
"""
import os
import re
import logging
import platform
import shutil
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from pathlib import Path

from agent.config import ActionType

logger = logging.getLogger(__name__)


DANGEROUS_PATH_PATTERNS: List[str] = [
    r"^/etc/",
    r"^/sys/",
    r"^/proc/",
    r"^/root/",
    r"^/boot/",
    r"^/dev/",
    r"^C:\\Windows\\",
    r"^C:\\Program Files\\",
    r"^C:\\Program Files \(x86\)\\",
    r"^C:\\Users\\All Users\\",
    r"\\.env$",
    r"\\.pem$",
    r"\\.key$",
    r"id_rsa",
    r"\\.git/",
    r"__pycache__/",
    r"\\.ssh/",
]

DANGEROUS_PATHS: List[str] = [
    "/etc/passwd",
    "/etc/shadow",
    "/etc/sudoers",
    "/etc/ssh/",
    "C:\\Windows\\System32\\config\\",
    "C:\\Windows\\System32\\drivers\\",
]


def get_desktop_path() -> str:
    """获取桌面路径"""
    system = platform.system()
    if system == "Windows":
        return str(Path.home() / "Desktop")
    elif system == "Darwin":
        return str(Path.home() / "Desktop")
    else:
        return str(Path.home() / "Desktop")


def get_recycle_bin_path() -> Path:
    """获取回收站路径"""
    system = platform.system()
    if system == "Windows":
        recycle_path = Path.home() / ".finetune_recycle_bin"
    else:
        recycle_path = Path.home() / ".finetune_recycle_bin"
    recycle_path.mkdir(parents=True, exist_ok=True)
    return recycle_path


@dataclass
class FileResult:
    """文件操作结果"""
    success: bool
    action: str
    description: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    feedback: str = ""


class FileExecutor:
    """
    文件操作执行器
    
    支持创建、读取、写入、删除文件
    所有操作都会进行安全路径检查
    """
    
    SAFE_PATHS = None
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    MAX_LIST_FILES = 1000  # 最大列出文件数
    
    def __init__(self, base_path: str = "."):
        self.base_path = Path(base_path).resolve()
        self._init_safe_paths()
        self._recycle_bin = get_recycle_bin_path()
        logger.info(f"文件执行器初始化，基础路径: {self.base_path}")
    
    def _init_safe_paths(self):
        """初始化安全路径列表"""
        if FileExecutor.SAFE_PATHS is None:
            FileExecutor.SAFE_PATHS = [
                self.base_path,
                Path(get_desktop_path()),
                Path.home() / "Documents",
                Path.home() / "Downloads",
                Path.home() / "Desktop",
            ]
    
    def _resolve_path(self, file_path: str) -> Path:
        """解析文件路径，确保在安全范围内"""
        path = Path(file_path)
        if not path.is_absolute():
            path = self.base_path / path
        return path.resolve()
    
    def _is_safe_path(self, path: Path) -> bool:
        """检查路径是否安全（在安全路径内且不在危险路径）"""
        try:
            resolved = path.resolve()
            path_str = str(resolved)
            
            for dangerous_path in DANGEROUS_PATHS:
                if path_str.startswith(dangerous_path) or dangerous_path in path_str:
                    logger.warning(f"访问危险路径被拒绝: {path_str}")
                    return False
            
            for pattern in DANGEROUS_PATH_PATTERNS:
                if re.search(pattern, path_str, re.IGNORECASE):
                    logger.warning(f"路径匹配危险模式被拒绝: {path_str} (模式: {pattern})")
                    return False
            
            for safe_path in self.SAFE_PATHS:
                try:
                    resolved.relative_to(safe_path.resolve())
                    return True
                except ValueError:
                    continue
            
            desktop = Path(get_desktop_path()).resolve()
            try:
                resolved.relative_to(desktop)
                return True
            except ValueError:
                pass
            
            logger.warning(f"路径不在安全范围内: {path_str}")
            return False
        except Exception as e:
            logger.error(f"路径安全检查异常: {e}")
            return False
    
    def _validate_file_size(self, path: Path) -> bool:
        """验证文件大小"""
        try:
            if path.exists() and path.is_file():
                size = path.stat().st_size
                if size > self.MAX_FILE_SIZE:
                    return False
            return True
        except Exception:
            return True
    
    def _move_to_recycle_bin(self, path: Path) -> bool:
        """将文件移动到回收站"""
        try:
            if not path.exists():
                return False
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            recycled_name = f"{path.name}_{timestamp}"
            recycled_path = self._recycle_bin / recycled_name
            
            shutil.move(str(path), str(recycled_path))
            logger.info(f"文件已移至回收站: {path} -> {recycled_path}")
            return True
        except Exception as e:
            logger.error(f"移动到回收站失败: {e}")
            return False
    
    async def execute(self, action: ActionType, params: Dict[str, Any]) -> FileResult:
        """执行文件操作"""
        try:
            file_path = params.get("path", params.get("file_path", ""))
            if file_path:
                path = self._resolve_path(file_path)
                if not self._is_safe_path(path):
                    return FileResult(
                        success=False,
                        action=action.value if hasattr(action, 'value') else str(action),
                        description="安全检查失败",
                        error=f"路径不在安全范围内或属于危险路径: {file_path}",
                        feedback="❌ 出于安全考虑，无法访问该路径。请使用桌面、文档或下载目录中的文件。"
                    )
            
            if action == ActionType.FILE_CREATE:
                return await self._create_file(params)
            elif action == ActionType.FILE_READ:
                return await self._read_file(params)
            elif action == ActionType.FILE_WRITE:
                return await self._write_file(params)
            elif action == ActionType.FILE_DELETE:
                return await self._delete_file(params)
            elif action == ActionType.FILE_LIST:
                return await self._list_files(params)
            else:
                return FileResult(
                    success=False,
                    action=action.value,
                    description="未知文件操作",
                    error=f"不支持的文件操作: {action.value}",
                    feedback=f"❌ 未知文件操作: {action.value}"
                )
        except Exception as e:
            logger.error(f"文件操作失败: {e}", exc_info=True)
            return FileResult(
                success=False,
                action=action.value if hasattr(action, 'value') else str(action),
                description="文件操作失败",
                error=str(e),
                feedback=f"❌ 操作失败: {str(e)}"
            )
    
    async def _create_file(self, params: Dict[str, Any]) -> FileResult:
        """创建文件"""
        file_path = params.get("path", params.get("file_path", ""))
        content = params.get("content", "")
        
        if not file_path:
            return FileResult(
                success=False,
                action="file_create",
                description="创建文件",
                error="未指定文件路径",
                feedback="❌ 请指定要创建的文件路径"
            )
        
        path = self._resolve_path(file_path)
        
        if not self._is_safe_path(path):
            return FileResult(
                success=False,
                action="file_create",
                description="创建文件",
                error=f"路径不在安全范围内: {path}",
                feedback="❌ 出于安全考虑，无法在该路径创建文件。请使用桌面、文档或下载目录。"
            )
        
        path.parent.mkdir(parents=True, exist_ok=True)
        
        if path.exists():
            return FileResult(
                success=False,
                action="file_create",
                description="创建文件",
                error=f"文件已存在: {path}",
                feedback=f"❌ 文件已存在: {file_path}"
            )
        
        path.write_text(content, encoding='utf-8')
        
        return FileResult(
            success=True,
            action="file_create",
            description="创建文件",
            data={"path": str(path), "size": len(content)},
            feedback=f"✅ 文件创建成功: {file_path}"
        )
    
    async def _read_file(self, params: Dict[str, Any]) -> FileResult:
        """读取文件"""
        file_path = params.get("path", params.get("file_path", ""))
        
        if not file_path:
            return FileResult(
                success=False,
                action="file_read",
                description="读取文件",
                error="未指定文件路径",
                feedback="❌ 请指定要读取的文件路径"
            )
        
        path = self._resolve_path(file_path)
        
        if not self._is_safe_path(path):
            return FileResult(
                success=False,
                action="file_read",
                description="读取文件",
                error=f"路径不在安全范围内: {path}",
                feedback="❌ 出于安全考虑，无法读取该文件。请使用桌面、文档或下载目录中的文件。"
            )
        
        if not path.exists():
            return FileResult(
                success=False,
                action="file_read",
                description="读取文件",
                error=f"文件不存在: {path}",
                feedback=f"❌ 文件不存在: {file_path}。请检查文件名是否正确，或使用'列出当前目录'查看可用文件。"
            )
        
        if not self._validate_file_size(path):
            return FileResult(
                success=False,
                action="file_read",
                description="读取文件",
                error=f"文件过大: {path}",
                feedback=f"❌ 文件过大（超过{self.MAX_FILE_SIZE // (1024*1024)}MB），无法读取。"
            )
        
        try:
            content = path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            return FileResult(
                success=False,
                action="file_read",
                description="读取文件",
                error=f"无法读取文件（非文本文件或编码不支持）: {path}",
                feedback=f"❌ 无法读取此文件（非文本文件或编码不支持）。"
            )
        
        return FileResult(
            success=True,
            action="file_read",
            description="读取文件",
            data={
                "path": str(path),
                "content": content[:5000],
                "size": len(content),
                "truncated": len(content) > 5000
            },
            feedback=f"✅ 文件读取成功: {file_path} ({len(content)} 字符)"
        )
    
    async def _write_file(self, params: Dict[str, Any]) -> FileResult:
        """写入文件"""
        file_path = params.get("path", params.get("file_path", ""))
        content = params.get("content", "")
        mode = params.get("mode", "write")
        is_desktop = params.get("is_desktop", False)
        
        if not file_path:
            return FileResult(
                success=False,
                action="file_write",
                description="保存文件",
                error="未指定文件路径",
                feedback="❌ 请指定要保存的文件路径"
            )
        
        path = self._resolve_path(file_path)
        
        if not self._is_safe_path(path):
            return FileResult(
                success=False,
                action="file_write",
                description="保存文件",
                error=f"路径不在安全范围内: {path}",
                feedback="❌ 出于安全考虑，无法保存到该路径。请使用桌面、文档或下载目录。"
            )
        
        desktop_path = Path(get_desktop_path()).resolve()
        is_on_desktop = False
        try:
            path.relative_to(desktop_path)
            is_on_desktop = True
        except ValueError:
            pass
        
        path.parent.mkdir(parents=True, exist_ok=True)
        
        if mode == "append":
            existing_content = ""
            if path.exists():
                existing_content = path.read_text(encoding='utf-8')
            content = existing_content + content
        
        path.write_text(content, encoding='utf-8')
        
        action_desc = "追加内容" if mode == "append" else "保存文件"
        location_desc = "桌面" if is_on_desktop or is_desktop else str(path.parent)
        
        return FileResult(
            success=True,
            action="file_write",
            description=action_desc,
            data={"path": str(path), "size": len(content), "mode": mode, "is_desktop": is_on_desktop},
            feedback=f"✅ {action_desc}成功！文件已保存到 {location_desc}\n📄 文件名: {path.name}\n📊 大小: {len(content)} 字符"
        )
    
    async def _delete_file(self, params: Dict[str, Any]) -> FileResult:
        """删除文件（移动到回收站）"""
        file_path = params.get("path", params.get("file_path", ""))
        use_recycle_bin = params.get("use_recycle_bin", True)
        
        if not file_path:
            return FileResult(
                success=False,
                action="file_delete",
                description="删除文件",
                error="未指定文件路径",
                feedback="❌ 请指定要删除的文件路径"
            )
        
        path = self._resolve_path(file_path)
        
        if not self._is_safe_path(path):
            return FileResult(
                success=False,
                action="file_delete",
                description="删除文件",
                error=f"路径不在安全范围内: {path}",
                feedback="❌ 出于安全考虑，无法删除该文件。"
            )
        
        if not path.exists():
            return FileResult(
                success=False,
                action="file_delete",
                description="删除文件",
                error=f"文件不存在: {path}",
                feedback=f"❌ 文件不存在: {file_path}"
            )
        
        if use_recycle_bin:
            if self._move_to_recycle_bin(path):
                return FileResult(
                    success=True,
                    action="file_delete",
                    description="删除文件",
                    data={"path": str(path), "recycled": True},
                    feedback=f"✅ 文件已移至回收站: {file_path}。如需恢复，请查看 ~/.finetune_recycle_bin 目录。"
                )
            else:
                path.unlink()
                return FileResult(
                    success=True,
                    action="file_delete",
                    description="删除文件",
                    data={"path": str(path), "recycled": False},
                    feedback=f"✅ 文件删除成功: {file_path}"
                )
        else:
            path.unlink()
            return FileResult(
                success=True,
                action="file_delete",
                description="删除文件",
                data={"path": str(path)},
                feedback=f"✅ 文件删除成功: {file_path}"
            )
    
    async def _list_files(self, params: Dict[str, Any]) -> FileResult:
        """列出文件"""
        dir_path = params.get("path", params.get("dir_path", "."))
        page = params.get("page", 1)
        page_size = params.get("page_size", 100)
        
        path = self._resolve_path(dir_path)
        
        if not self._is_safe_path(path):
            return FileResult(
                success=False,
                action="file_list",
                description="列出文件",
                error=f"路径不在安全范围内: {path}",
                feedback="❌ 出于安全考虑，无法访问该目录。"
            )
        
        if not path.exists():
            return FileResult(
                success=False,
                action="file_list",
                description="列出文件",
                error=f"目录不存在: {path}",
                feedback=f"❌ 目录不存在: {dir_path}"
            )
        
        if not path.is_dir():
            return FileResult(
                success=False,
                action="file_list",
                description="列出文件",
                error=f"不是目录: {path}",
                feedback=f"❌ 不是目录: {dir_path}"
            )
        
        all_items = list(path.iterdir())
        total_count = len(all_items)
        
        start = (page - 1) * page_size
        end = start + page_size
        paginated_items = all_items[start:end]
        
        files = []
        for item in paginated_items:
            try:
                files.append({
                    "name": item.name,
                    "type": "directory" if item.is_dir() else "file",
                    "size": item.stat().st_size if item.is_file() else None,
                    "modified": datetime.fromtimestamp(item.stat().st_mtime).isoformat() if item.exists() else None
                })
            except Exception:
                files.append({
                    "name": item.name,
                    "type": "directory" if item.is_dir() else "file",
                    "size": None,
                    "modified": None
                })
        
        return FileResult(
            success=True,
            action="file_list",
            description="列出文件",
            data={
                "path": str(path),
                "files": files,
                "count": len(files),
                "total_count": total_count,
                "page": page,
                "page_size": page_size,
                "total_pages": (total_count + page_size - 1) // page_size
            },
            feedback=f"✅ 找到 {total_count} 个项目，显示第 {page} 页（{len(files)} 个）"
        )
    
    def restore_from_recycle_bin(self, original_name: str, restore_path: str) -> FileResult:
        """从回收站恢复文件"""
        try:
            recycled_files = list(self._recycle_bin.glob(f"{original_name}_*"))
            
            if not recycled_files:
                return FileResult(
                    success=False,
                    action="file_restore",
                    description="恢复文件",
                    error=f"回收站中未找到文件: {original_name}",
                    feedback=f"❌ 回收站中未找到文件: {original_name}"
                )
            
            latest_file = max(recycled_files, key=lambda f: f.stat().st_mtime)
            restore_target = self._resolve_path(restore_path)
            
            if not self._is_safe_path(restore_target):
                return FileResult(
                    success=False,
                    action="file_restore",
                    description="恢复文件",
                    error=f"恢复路径不在安全范围内: {restore_path}",
                    feedback="❌ 恢复路径不在安全范围内。"
                )
            
            shutil.move(str(latest_file), str(restore_target))
            
            return FileResult(
                success=True,
                action="file_restore",
                description="恢复文件",
                data={"from": str(latest_file), "to": str(restore_target)},
                feedback=f"✅ 文件已恢复: {restore_path}"
            )
        except Exception as e:
            logger.error(f"恢复文件失败: {e}")
            return FileResult(
                success=False,
                action="file_restore",
                description="恢复文件",
                error=str(e),
                feedback=f"❌ 恢复失败: {str(e)}"
            )


_file_executor: Optional[FileExecutor] = None


def get_file_executor() -> FileExecutor:
    """获取文件执行器单例"""
    global _file_executor
    if _file_executor is None:
        _file_executor = FileExecutor()
    return _file_executor
