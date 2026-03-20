"""
文件读取技�?读取文件内容并返�?"""
from typing import Dict, Any, Optional
from pathlib import Path

from skills.base import SkillBase
from skills.models import SkillMetadata, SkillParameter, SkillResult, SkillCategory


class FileReadSkill(SkillBase):
    """文件读取技�?""
    
    metadata = SkillMetadata(
        name="file_read",
        display_name="文件读取",
        description="读取文件内容并返�?,
        version="1.0.0",
        category=SkillCategory.FILE,
        parameters=[
            SkillParameter(
                name="file_path",
                type="string",
                description="要读取的文件路径",
                required=True,
            ),
            SkillParameter(
                name="encoding",
                type="string",
                description="文件编码",
                required=False,
                default="utf-8",
            ),
        ],
        tags=["file", "read", "io"],
    )
    
    async def execute(self, **kwargs) -> SkillResult:
        file_path = kwargs.get("file_path")
        encoding = kwargs.get("encoding", "utf-8")
        
        if not file_path:
            return SkillResult(
                success=False,
                error="缺少 file_path 参数",
                error_code="MISSING_PARAMETER",
            )
        
        try:
            path = Path(file_path)
            
            if not path.exists():
                return SkillResult(
                    success=False,
                    error=f"文件不存�? {file_path}",
                    error_code="FILE_NOT_FOUND",
                )
            
            if not path.is_file():
                return SkillResult(
                    success=False,
                    error=f"路径不是文件: {file_path}",
                    error_code="NOT_A_FILE",
                )
            
            content = path.read_text(encoding=encoding)
            
            return SkillResult(
                success=True,
                data={
                    "content": content,
                    "size": len(content),
                    "path": str(path.absolute()),
                },
                message=f"成功读取文件: {file_path}",
            )
            
        except Exception as e:
            return SkillResult(
                success=False,
                error=str(e),
                error_code="READ_ERROR",
            )


def get_skill():
    return FileReadSkill()
