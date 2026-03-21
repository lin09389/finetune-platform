# -*- coding: utf-8 -*-
"""
文件操作沙箱 - 限制文件访问范围

功能：
- 工作目录限制（禁止访问目录外文件）
- 路径遍历检测（禁止 ..）
- 危险文件类型拦截
- 文件大小限制
"""
from pathlib import Path
import os
import re
from typing import Set, List, Optional
import logging

logger = logging.getLogger(__name__)


class FileSandbox:
    """文件操作沙箱"""

    FORBIDDEN_PATTERNS = [
        r'\.\.',
        r'^/etc/',
        r'^/usr/',
        r'^/var/',
        r'^/root/',
        r'^C:/Windows/',
        r'^C:/Program Files/',
        r'^C:/ProgramData/',
    ]

    ALLOWED_OPERATIONS = {'read', 'write', 'create', 'delete', 'list'}

    ALLOWED_EXTENSIONS = {
        '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.go', '.rs', '.c', '.cpp', '.h',
        '.json', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf',
        '.md', '.txt', '.rst', '.doc', '.docx',
        '.csv', '.xml', '.sql',
        '.html', '.css', '.scss', '.less',
        '.sh', '.bat', '.ps1',
    }

    DANGEROUS_EXTENSIONS = {
        '.exe', '.dll', '.so', '.dylib',
        '.com', '.scr', '.pif',
        '.vbs', '.vbe', '.js', '.jse',
        '.wsf', '.wsc', '.wsh',
        '.msi', '.msp', '.mst',
        '.cmd', '.bat', '.ps1',
    }

    MAX_FILE_SIZE = 10 * 1024 * 1024

    def __init__(self, working_dir: Optional[str] = None):
        if working_dir:
            self.working_dir = Path(working_dir).resolve()
        else:
            self.working_dir = Path(__file__).parent.parent.resolve()

        logger.info(f"文件沙箱已初始化，工作目录：{self.working_dir}")

    def safe_path(self, file_path: str, operation: str = 'read') -> Path:
        if operation not in self.ALLOWED_OPERATIONS:
            raise PermissionError(f"不允许的操作：{operation}")

        if os.path.isabs(file_path):
            path = Path(file_path).resolve()
        else:
            path = (self.working_dir / file_path).resolve()

        try:
            path.relative_to(self.working_dir)
        except ValueError:
            raise PermissionError(
                f"禁止访问工作目录外的文件：{file_path}\n"
                f"工作目录：{self.working_dir}"
            )

        path_str = str(path).replace('\\', '/')
        for pattern in self.FORBIDDEN_PATTERNS:
            if re.search(pattern, path_str, re.IGNORECASE):
                raise PermissionError(f"禁止访问的路径：{file_path}")

        if operation in ['write', 'create']:
            ext = path.suffix.lower()
            if ext in self.DANGEROUS_EXTENSIONS:
                raise PermissionError(
                    f"禁止创建危险文件类型：{ext}\n"
                    f"如需创建可执行文件，请手动操作"
                )

        return path

    def read_file(self, file_path: str, max_size: int = None) -> str:
        if max_size is None:
            max_size = self.MAX_FILE_SIZE

        path = self.safe_path(file_path, 'read')

        if not path.exists():
            raise FileNotFoundError(f"文件不存在：{file_path}")

        file_size = path.stat().st_size
        if file_size > max_size:
            raise PermissionError(
                f"文件过大：{file_size/1024/1024:.2f}MB\n"
                f"最大允许：{max_size/1024/1024:.2f}MB"
            )

        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            logger.info(f"读取文件：{file_path} ({file_size} bytes)")
            return content
        except Exception as e:
            logger.error(f"读取文件失败：{e}")
            raise

    def write_file(self, file_path: str, content: str) -> str:
        path = self.safe_path(file_path, 'write')

        ext = path.suffix.lower()
        if ext not in self.ALLOWED_EXTENSIONS:
            raise PermissionError(
                f"不允许的文件类型：{ext}\n"
                f"允许的扩展名：{', '.join(sorted(self.ALLOWED_EXTENSIONS))}"
            )

        path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            logger.info(f"写入文件：{file_path} ({len(content)} bytes)")
            return str(path)
        except Exception as e:
            logger.error(f"写入文件失败：{e}")
            raise

    def create_file(self, file_path: str, content: str = "") -> str:
        return self.write_file(file_path, content)

    def delete_file(self, file_path: str) -> bool:
        path = self.safe_path(file_path, 'delete')

        if path.is_dir():
            raise PermissionError("禁止删除目录，请使用其他方式")

        try:
            path.unlink()
            logger.info(f"删除文件：{file_path}")
            return True
        except Exception as e:
            logger.error(f"删除文件失败：{e}")
            raise

    def list_files(self, directory: str = ".", pattern: str = "*") -> list:
        dir_path = self.safe_path(directory, 'list')

        if not dir_path.is_dir():
            raise ValueError(f"不是目录：{directory}")

        files = []
        for item in dir_path.glob(pattern):
            if item.name.startswith('.'):
                continue

            try:
                rel_path = item.relative_to(self.working_dir)
                files.append({
                    'name': item.name,
                    'path': str(rel_path),
                    'is_dir': item.is_dir(),
                    'size': item.stat().st_size if item.is_file() else 0,
                    'extension': item.suffix.lower() if item.is_file() else ''
                })
            except ValueError:
                continue

        files.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))

        logger.info(f"列出文件：{directory} ({len(files)} 项)")
        return files

    def file_exists(self, file_path: str) -> bool:
        try:
            path = self.safe_path(file_path, 'read')
            return path.exists()
        except Exception as e:
            logger.debug(f"检查文件存在失败：{e}")
            return False

    def get_allowed_extensions(self) -> Set[str]:
        return self.ALLOWED_EXTENSIONS.copy()

    def get_working_dir(self) -> str:
        return str(self.working_dir)

    def get_sandbox_info(self) -> dict:
        return {
            'working_dir': str(self.working_dir),
            'allowed_operations': list(self.ALLOWED_OPERATIONS),
            'max_file_size_mb': self.MAX_FILE_SIZE / 1024 / 1024,
            'allowed_extensions_count': len(self.ALLOWED_EXTENSIONS),
            'forbidden_patterns_count': len(self.FORBIDDEN_PATTERNS),
        }


file_sandbox = FileSandbox()
