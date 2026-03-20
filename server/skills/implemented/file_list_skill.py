"""
文件列表技�?列出目录中的文件和子目录
"""
from typing import Dict, Any, Optional, List
from pathlib import Path

from skills.base import SkillBase
from skills.models import SkillMetadata, SkillParameter, SkillResult, SkillCategory


class FileListSkill(SkillBase):
    """列出目录文件技�?""
    
    metadata = SkillMetadata(
        name="file_list",
        display_name="列出文件",
        description="列出目录中的文件和子目录",
        version="1.0.0",
        category=SkillCategory.FILE,
        parameters=[
            SkillParameter(
                name="directory",
                type="string",
                description="要列出的目录路径",
                required=False,
                default=".",
            ),
            SkillParameter(
                name="pattern",
                type="string",
                description="文件匹配模式 (glob)",
                required=False,
                default="*",
            ),
            SkillParameter(
                name="recursive",
                type="boolean",
                description="是否递归列出",
                required=False,
                default=False,
            ),
        ],
        tags=["file", "list", "directory", "io"],
    )
    
    async def execute(self, **kwargs) -> SkillResult:
        directory = kwargs.get("directory", ".")
        pattern = kwargs.get("pattern", "*")
        recursive = kwargs.get("recursive", False)
        
        try:
            path = Path(directory)
            
            if not path.exists():
                return SkillResult(
                    success=False,
                    error=f"目录不存�? {directory}",
                    error_code="DIR_NOT_FOUND",
                )
            
            if not path.is_dir():
                return SkillResult(
                    success=False,
                    error=f"路径不是目录: {directory}",
                    error_code="NOT_A_DIR",
                )
            
            files = []
            
            if recursive:
                for item in path.rglob(pattern):
                    files.append({
                        "name": item.name,
                        "path": str(item.relative_to(path)),
                        "is_dir": item.is_dir(),
                        "size": item.stat().st_size if item.is_file() else 0,
                    })
            else:
                for item in path.glob(pattern):
                    files.append({
                        "name": item.name,
                        "path": str(item),
                        "is_dir": item.is_dir(),
                        "size": item.stat().st_size if item.is_file() else 0,
                    })
            
            return SkillResult(
                success=True,
                data={
                    "files": files,
                    "count": len(files),
                    "directory": str(path.absolute()),
                },
                message=f"找到 {len(files)} 个项�?,
            )
            
        except Exception as e:
            return SkillResult(
                success=False,
                error=str(e),
                error_code="LIST_ERROR",
            )


def get_skill():
    return FileListSkill()
