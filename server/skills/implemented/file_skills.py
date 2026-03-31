"""
基础文件操作技能
"""
import shutil
from pathlib import Path

from skills.base import SkillBase
from skills.models import (
    SkillCategory,
    SkillMetadata,
    SkillParameter,
    SkillParameterType,
    SkillResult,
)


class FileReadSkill(SkillBase):
    """读取文件内容"""

    @classmethod
    def get_metadata(cls) -> SkillMetadata:
        return SkillMetadata(
            name="file_read",
            display_name="读取文件",
            description="读取指定路径的文件内容",
            version="1.0.0",
            category=SkillCategory.FILE,
            tags=["file", "read", "text"],
            parameters=[
                SkillParameter(
                    name="file_path",
                    type=SkillParameterType.STRING,
                    description="文件路径",
                    required=True,
                ),
                SkillParameter(
                    name="encoding",
                    type=SkillParameterType.STRING,
                    description="文件编码",
                    required=False,
                    default="utf-8",
                ),
                SkillParameter(
                    name="max_size",
                    type=SkillParameterType.INTEGER,
                    description="最大读取大小（字节）",
                    required=False,
                    default=1048576,
                ),
            ],
            examples=[
                {"file_path": "/path/to/file.txt"},
                {"file_path": "/path/to/file.txt", "encoding": "gbk"},
            ],
        )

    async def execute(self, **kwargs) -> SkillResult:
        file_path = kwargs.get("file_path")
        encoding = kwargs.get("encoding", "utf-8")
        max_size = kwargs.get("max_size", 1048576)

        try:
            path = Path(file_path)

            if not path.exists():
                return SkillResult(
                    success=False,
                    error=f"文件不存在: {file_path}",
                    error_code="FILE_NOT_FOUND",
                )

            if not path.is_file():
                return SkillResult(
                    success=False,
                    error=f"路径不是文件: {file_path}",
                    error_code="NOT_A_FILE",
                )

            file_size = path.stat().st_size
            if file_size > max_size:
                return SkillResult(
                    success=False,
                    error=f"文件过大: {file_size} 字节，最大允许: {max_size} 字节",
                    error_code="FILE_TOO_LARGE",
                )

            content = path.read_text(encoding=encoding)

            return SkillResult(
                success=True,
                data={
                    "content": content,
                    "size": file_size,
                    "path": str(path.absolute()),
                    "encoding": encoding,
                },
            )

        except Exception as e:
            return SkillResult(
                success=False,
                error=f"读取文件失败: {str(e)}",
                error_code="READ_ERROR",
            )


class FileWriteSkill(SkillBase):
    """写入文件内容"""

    @classmethod
    def get_metadata(cls) -> SkillMetadata:
        return SkillMetadata(
            name="file_write",
            display_name="写入文件",
            description="将内容写入指定路径的文件",
            version="1.0.0",
            category=SkillCategory.FILE,
            tags=["file", "write", "text"],
            parameters=[
                SkillParameter(
                    name="file_path",
                    type=SkillParameterType.STRING,
                    description="文件路径",
                    required=True,
                ),
                SkillParameter(
                    name="content",
                    type=SkillParameterType.STRING,
                    description="要写入的内容",
                    required=True,
                ),
                SkillParameter(
                    name="encoding",
                    type=SkillParameterType.STRING,
                    description="文件编码",
                    required=False,
                    default="utf-8",
                ),
                SkillParameter(
                    name="mode",
                    type=SkillParameterType.STRING,
                    description="写入模式: write(覆盖) 或 append(追加)",
                    required=False,
                    default="write",
                    enum=["write", "append"],
                ),
            ],
            examples=[
                {"file_path": "/path/to/file.txt", "content": "Hello World"},
                {"file_path": "/path/to/file.txt", "content": "More text", "mode": "append"},
            ],
        )

    async def execute(self, **kwargs) -> SkillResult:
        file_path = kwargs.get("file_path")
        content = kwargs.get("content", "")
        encoding = kwargs.get("encoding", "utf-8")
        mode = kwargs.get("mode", "write")

        try:
            path = Path(file_path)

            path.parent.mkdir(parents=True, exist_ok=True)

            write_mode = "a" if mode == "append" else "w"
            with open(path, write_mode, encoding=encoding) as f:
                f.write(content)

            file_size = path.stat().st_size

            return SkillResult(
                success=True,
                data={
                    "path": str(path.absolute()),
                    "size": file_size,
                    "mode": mode,
                },
            )

        except Exception as e:
            return SkillResult(
                success=False,
                error=f"写入文件失败: {str(e)}",
                error_code="WRITE_ERROR",
            )


class FileListSkill(SkillBase):
    """列出目录内容"""

    @classmethod
    def get_metadata(cls) -> SkillMetadata:
        return SkillMetadata(
            name="file_list",
            display_name="列出目录",
            description="列出指定目录下的文件和子目录",
            version="1.0.0",
            category=SkillCategory.FILE,
            tags=["file", "directory", "list"],
            parameters=[
                SkillParameter(
                    name="directory",
                    type=SkillParameterType.STRING,
                    description="目录路径",
                    required=True,
                ),
                SkillParameter(
                    name="pattern",
                    type=SkillParameterType.STRING,
                    description="文件匹配模式（如 *.txt）",
                    required=False,
                    default="*",
                ),
                SkillParameter(
                    name="recursive",
                    type=SkillParameterType.BOOLEAN,
                    description="是否递归列出子目录",
                    required=False,
                    default=False,
                ),
            ],
            examples=[
                {"directory": "/path/to/dir"},
                {"directory": "/path/to/dir", "pattern": "*.py", "recursive": True},
            ],
        )

    async def execute(self, **kwargs) -> SkillResult:
        directory = kwargs.get("directory")
        pattern = kwargs.get("pattern", "*")
        recursive = kwargs.get("recursive", False)

        try:
            path = Path(directory)

            if not path.exists():
                return SkillResult(
                    success=False,
                    error=f"目录不存在: {directory}",
                    error_code="DIR_NOT_FOUND",
                )

            if not path.is_dir():
                return SkillResult(
                    success=False,
                    error=f"路径不是目录: {directory}",
                    error_code="NOT_A_DIR",
                )

            items = []

            if recursive:
                for item in path.rglob(pattern):
                    items.append({
                        "name": item.name,
                        "path": str(item.relative_to(path)),
                        "absolute_path": str(item.absolute()),
                        "type": "directory" if item.is_dir() else "file",
                        "size": item.stat().st_size if item.is_file() else None,
                    })
            else:
                for item in path.glob(pattern):
                    items.append({
                        "name": item.name,
                        "path": item.name,
                        "absolute_path": str(item.absolute()),
                        "type": "directory" if item.is_dir() else "file",
                        "size": item.stat().st_size if item.is_file() else None,
                    })

            return SkillResult(
                success=True,
                data={
                    "directory": str(path.absolute()),
                    "items": items,
                    "count": len(items),
                },
            )

        except Exception as e:
            return SkillResult(
                success=False,
                error=f"列出目录失败: {str(e)}",
                error_code="LIST_ERROR",
            )


class FileDeleteSkill(SkillBase):
    """删除文件或目录"""

    @classmethod
    def get_metadata(cls) -> SkillMetadata:
        return SkillMetadata(
            name="file_delete",
            display_name="删除文件",
            description="删除指定的文件或目录",
            version="1.0.0",
            category=SkillCategory.FILE,
            tags=["file", "delete", "remove"],
            parameters=[
                SkillParameter(
                    name="path",
                    type=SkillParameterType.STRING,
                    description="文件或目录路径",
                    required=True,
                ),
                SkillParameter(
                    name="recursive",
                    type=SkillParameterType.BOOLEAN,
                    description="是否递归删除目录",
                    required=False,
                    default=False,
                ),
            ],
            examples=[
                {"path": "/path/to/file.txt"},
                {"path": "/path/to/dir", "recursive": True},
            ],
            requires_confirmation=True,
        )

    async def execute(self, **kwargs) -> SkillResult:
        file_path = kwargs.get("path")
        recursive = kwargs.get("recursive", False)

        try:
            path = Path(file_path)

            if not path.exists():
                return SkillResult(
                    success=False,
                    error=f"路径不存在: {file_path}",
                    error_code="PATH_NOT_FOUND",
                )

            if path.is_file():
                path.unlink()
                return SkillResult(
                    success=True,
                    data={
                        "path": str(path.absolute()),
                        "type": "file",
                        "action": "deleted",
                    },
                )

            if path.is_dir():
                if not recursive and any(path.iterdir()):
                    return SkillResult(
                        success=False,
                        error="目录不为空，需要设置 recursive=True",
                        error_code="DIR_NOT_EMPTY",
                    )

                shutil.rmtree(path) if recursive else path.rmdir()

                return SkillResult(
                    success=True,
                    data={
                        "path": str(path.absolute()),
                        "type": "directory",
                        "action": "deleted",
                        "recursive": recursive,
                    },
                )

        except Exception as e:
            return SkillResult(
                success=False,
                error=f"删除失败: {str(e)}",
                error_code="DELETE_ERROR",
            )
