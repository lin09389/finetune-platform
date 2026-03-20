"""
文件操作沙箱 - 限制文件访问范围

功能�?- 工作目录限制（禁止访问目录外文件�?- 路径遍历检测（禁止 ..�?- 危险文件类型拦截
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

    # 禁止访问的路径模式（黑名单）
    FORBIDDEN_PATTERNS = [
        r'\.\.',  # 目录遍历
        r'^/etc/',
        r'^/usr/',
        r'^/var/',
        r'^/root/',
        r'^C:/Windows/',
        r'^C:/Program Files/',
        r'^C:/ProgramData/',
    ]

    # 允许的操�?    ALLOWED_OPERATIONS = {'read', 'write', 'create', 'delete', 'list'}

    # 允许的文件扩展名（创�?写入�?    ALLOWED_EXTENSIONS = {
        # 代码文件
        '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.go', '.rs', '.c', '.cpp', '.h',
        # 配置文件
        '.json', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf',
        # 文档文件
        '.md', '.txt', '.rst', '.doc', '.docx',
        # 数据文件
        '.csv', '.xml', '.sql',
        # 网页文件
        '.html', '.css', '.scss', '.less',
        # 脚本文件
        '.sh', '.bat', '.ps1',
    }

    # 危险扩展名（禁止创建�?    DANGEROUS_EXTENSIONS = {
        '.exe', '.dll', '.so', '.dylib',  # 可执行文�?        '.com', '.scr', '.pif',  # Windows 脚本
        '.vbs', '.vbe', '.js', '.jse',  # 脚本病毒
        '.wsf', '.wsc', '.wsh',  # Windows 脚本
        '.msi', '.msp', '.mst',  # 安装程序
        '.cmd', '.bat', '.ps1',  # 批处理（允许读取，禁止创建）
    }

    # 最大文件大小（10MB�?    MAX_FILE_SIZE = 10 * 1024 * 1024

    def __init__(self, working_dir: Optional[str] = None):
        """
        初始化文件沙�?
        Args:
            working_dir: 工作目录（默认项目根目录�?        """
        if working_dir:
            self.working_dir = Path(working_dir).resolve()
        else:
            # 默认使用 server 目录的父目录
            self.working_dir = Path(__file__).parent.parent.resolve()

        logger.info(f"文件沙箱已初始化，工作目录：{self.working_dir}")

    def safe_path(self, file_path: str, operation: str = 'read') -> Path:
        """
        安全检查文件路�?
        Args:
            file_path: 文件路径（相对或绝对�?            operation: 操作类型 (read/write/create/delete/list)

        Returns:
            安全的路径对�?
        Raises:
            PermissionError: 访问被拒�?            ValueError: 路径无效
        """
        # 检查操作是否允�?        if operation not in self.ALLOWED_OPERATIONS:
            raise PermissionError(f"不允许的操作：{operation}")

        # 转换为绝对路�?        if os.path.isabs(file_path):
            path = Path(file_path).resolve()
        else:
            path = (self.working_dir / file_path).resolve()

        # 检查是否在工作目录�?        try:
            path.relative_to(self.working_dir)
        except ValueError:
            raise PermissionError(
                f"禁止访问工作目录外的文件：{file_path}\n"
                f"工作目录：{self.working_dir}"
            )

        # 检查禁止模�?        path_str = str(path).replace('\\', '/')
        for pattern in self.FORBIDDEN_PATTERNS:
            if re.search(pattern, path_str, re.IGNORECASE):
                raise PermissionError(f"禁止访问的路径：{file_path}")

        # 对于写操作，检查文件扩展名
        if operation in ['write', 'create']:
            ext = path.suffix.lower()
            
            # 检查危险扩展名
            if ext in self.DANGEROUS_EXTENSIONS:
                raise PermissionError(
                    f"禁止创建危险文件类型：{ext}\n"
                    f"如需创建可执行文件，请手动操�?
                )

        return path

    def read_file(self, file_path: str, max_size: int = None) -> str:
        """
        安全读取文件

        Args:
            file_path: 文件路径
            max_size: 最大文件大小（字节�?
        Returns:
            文件内容
        """
        if max_size is None:
            max_size = self.MAX_FILE_SIZE

        path = self.safe_path(file_path, 'read')

        # 检查文件是否存�?        if not path.exists():
            raise FileNotFoundError(f"文件不存在：{file_path}")

        # 检查文件大�?        file_size = path.stat().st_size
        if file_size > max_size:
            raise PermissionError(
                f"文件过大：{file_size/1024/1024:.2f}MB\n"
                f"最大允许：{max_size/1024/1024:.2f}MB"
            )

        # 读取文件
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            logger.info(f"读取文件：{file_path} ({file_size} bytes)")
            return content
        except Exception as e:
            logger.error(f"读取文件失败：{e}")
            raise

    def write_file(self, file_path: str, content: str) -> str:
        """
        安全写入文件

        Args:
            file_path: 文件路径
            content: 文件内容

        Returns:
            写入的文件路�?        """
        path = self.safe_path(file_path, 'write')

        # 检查扩展名
        ext = path.suffix.lower()
        if ext not in self.ALLOWED_EXTENSIONS:
            raise PermissionError(
                f"不允许的文件类型：{ext}\n"
                f"允许的扩展名：{', '.join(sorted(self.ALLOWED_EXTENSIONS))}"
            )

        # 创建父目�?        path.parent.mkdir(parents=True, exist_ok=True)

        # 写入文件
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            logger.info(f"写入文件：{file_path} ({len(content)} bytes)")
            return str(path)
        except Exception as e:
            logger.error(f"写入文件失败：{e}")
            raise

    def create_file(self, file_path: str, content: str = "") -> str:
        """
        安全创建文件

        Args:
            file_path: 文件路径
            content: 文件内容

        Returns:
            创建的文件路�?        """
        return self.write_file(file_path, content)

    def delete_file(self, file_path: str) -> bool:
        """
        安全删除文件

        Args:
            file_path: 文件路径

        Returns:
            是否删除成功
        """
        path = self.safe_path(file_path, 'delete')

        # 禁止删除目录
        if path.is_dir():
            raise PermissionError("禁止删除目录，请使用其他方式")

        # 删除文件
        try:
            path.unlink()
            logger.info(f"删除文件：{file_path}")
            return True
        except Exception as e:
            logger.error(f"删除文件失败：{e}")
            raise

    def list_files(self, directory: str = ".", pattern: str = "*") -> list:
        """
        安全列出文件

        Args:
            directory: 目录路径
            pattern: 文件匹配模式（支持通配符）

        Returns:
            文件信息列表
        """
        dir_path = self.safe_path(directory, 'list')

        if not dir_path.is_dir():
            raise ValueError(f"不是目录：{directory}")

        files = []
        for item in dir_path.glob(pattern):
            # 跳过隐藏文件
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
                # 文件不在工作目录内，跳过
                continue

        # 按名称排�?        files.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))

        logger.info(f"列出文件：{directory} ({len(files)} �?")
        return files

    def file_exists(self, file_path: str) -> bool:
        """检查文件是否存�?""
        try:
            path = self.safe_path(file_path, 'read')
            return path.exists()
        except Exception as e:
            logger.debug(f"检查文件存在失败：{e}")
            return False

    def get_allowed_extensions(self) -> Set[str]:
        """获取允许的扩展名列表"""
        return self.ALLOWED_EXTENSIONS.copy()

    def get_working_dir(self) -> str:
        """获取工作目录"""
        return str(self.working_dir)

    def get_sandbox_info(self) -> dict:
        """获取沙箱信息"""
        return {
            'working_dir': str(self.working_dir),
            'allowed_operations': list(self.ALLOWED_OPERATIONS),
            'max_file_size_mb': self.MAX_FILE_SIZE / 1024 / 1024,
            'allowed_extensions_count': len(self.ALLOWED_EXTENSIONS),
            'forbidden_patterns_count': len(self.FORBIDDEN_PATTERNS),
        }


# 全局单例
file_sandbox = FileSandbox()
