from .archive import ArchiveExecutor, ArchiveResult
from .batch import BatchFileExecutor, BatchItemResult, BatchResult
from .copy import CopyResult, FileCopyExecutor
from .directory import DirectoryExecutor, DirectoryInfo, DirectoryResult, TreeResult
from .handler import (
    DANGEROUS_PATH_PATTERNS,
    DANGEROUS_PATHS,
    FileExecutor,
    FileOperationHandler,
    get_desktop_path,
    get_file_executor,
    get_file_handler,
    get_recycle_bin_path,
)
from .move import FileMoveExecutor, MoveResult
from .rename import BatchRenameResult, FileRenameExecutor, RenameResult
from .search import FileSearchExecutor, SearchCriteria, SearchResult, SearchResults

FileCopyOperation = FileCopyExecutor
FileMoveOperation = FileMoveExecutor

__all__ = [
    "FileOperationHandler",
    "FileExecutor",
    "get_file_handler",
    "get_file_executor",
    "DANGEROUS_PATH_PATTERNS",
    "DANGEROUS_PATHS",
    "get_desktop_path",
    "get_recycle_bin_path",
    "FileCopyExecutor",
    "CopyResult",
    "FileMoveExecutor",
    "MoveResult",
    "FileRenameExecutor",
    "RenameResult",
    "BatchRenameResult",
    "DirectoryExecutor",
    "DirectoryResult",
    "DirectoryInfo",
    "TreeResult",
    "BatchFileExecutor",
    "BatchResult",
    "BatchItemResult",
    "FileSearchExecutor",
    "SearchResult",
    "SearchResults",
    "SearchCriteria",
    "ArchiveExecutor",
    "ArchiveResult",
    "FileCopyOperation",
    "FileMoveOperation",
]
