import asyncio
import base64
import io
import logging
import platform
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from agent.core.types import ErrorCode, ExecutionResult, ExecutionStatus

logger = logging.getLogger(__name__)


class ClipboardContentType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    FILES = "files"
    HTML = "html"
    RTF = "rtf"
    UNKNOWN = "unknown"


@dataclass
class ClipboardContent:
    content_type: ClipboardContentType
    data: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)
    size_bytes: int = 0
    format_name: str = ""


@dataclass
class ClipboardHistory:
    items: list[ClipboardContent] = field(default_factory=list)
    max_items: int = 100
    current_index: int = -1


class PlatformClipboard:
    @staticmethod
    def get_platform() -> str:
        system = platform.system().lower()
        if system == "darwin":
            return "macos"
        elif system == "windows":
            return "windows"
        elif system == "linux":
            return "linux"
        return system

    @staticmethod
    def is_windows() -> bool:
        return platform.system().lower() == "windows"

    @staticmethod
    def is_macos() -> bool:
        return platform.system().lower() == "darwin"

    @staticmethod
    def is_linux() -> bool:
        return platform.system().lower() == "linux"


class WindowsClipboardBackend:
    def __init__(self):
        self._win32clipboard = None
        self._win32con = None
        self._win32api = None
        self._initialized = False

    def _ensure_initialized(self) -> bool:
        if self._initialized:
            return True

        try:
            import win32api
            import win32clipboard
            import win32con
            self._win32clipboard = win32clipboard
            self._win32con = win32con
            self._win32api = win32api
            self._initialized = True
            return True
        except ImportError:
            logger.warning("pywin32 not available, using subprocess fallback")
            return False

    def read_text(self) -> str | None:
        if self._ensure_initialized():
            return self._read_text_win32()
        return self._read_text_powershell()

    def _read_text_win32(self) -> str | None:
        try:
            self._win32clipboard.OpenClipboard()
            try:
                if self._win32clipboard.IsClipboardFormatAvailable(self._win32con.CF_UNICODETEXT):
                    data = self._win32clipboard.GetClipboardData(self._win32con.CF_UNICODETEXT)
                    return data
                elif self._win32clipboard.IsClipboardFormatAvailable(self._win32con.CF_TEXT):
                    data = self._win32clipboard.GetClipboardData(self._win32con.CF_TEXT)
                    return data.decode("utf-8", errors="replace")
            finally:
                self._win32clipboard.CloseClipboard()
        except Exception as e:
            logger.error(f"Failed to read text from clipboard (win32): {e}")
        return None

    def _read_text_powershell(self) -> str | None:
        try:
            result = subprocess.run(
                ["powershell", "-command", "Get-Clipboard"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception as e:
            logger.error(f"Failed to read text from clipboard (powershell): {e}")
        return None

    def read_image(self) -> bytes | None:
        if self._ensure_initialized():
            return self._read_image_win32()
        return self._read_image_powershell()

    def _read_image_win32(self) -> bytes | None:
        try:
            from PIL import Image

            self._win32clipboard.OpenClipboard()
            try:
                if self._win32clipboard.IsClipboardFormatAvailable(self._win32con.CF_DIB):
                    data = self._win32clipboard.GetClipboardData(self._win32con.CF_DIB)
                    return self._dib_to_bytes(data)
                elif self._win32clipboard.IsClipboardFormatAvailable(self._win32con.CF_DIBV5):
                    data = self._win32clipboard.GetClipboardData(self._win32con.CF_DIBV5)
                    return self._dib_to_bytes(data)
            finally:
                self._win32clipboard.CloseClipboard()
        except ImportError:
            logger.warning("PIL not available for image conversion")
        except Exception as e:
            logger.error(f"Failed to read image from clipboard (win32): {e}")
        return None

    def _read_image_powershell(self) -> bytes | None:
        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-command",
                    "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Clipboard]::GetImage() | ForEach-Object { $_.Save([System.IO.MemoryStream]::new(), [System.Drawing.Imaging.ImageFormat]::Png) } | ForEach-Object { [Convert]::ToBase64String($_.ToArray()) }",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                return base64.b64decode(result.stdout.strip())
        except Exception as e:
            logger.error(f"Failed to read image from clipboard (powershell): {e}")
        return None

    def _dib_to_bytes(self, dib_data: bytes) -> bytes | None:
        try:
            from PIL import Image

            img = Image.open(io.BytesIO(dib_data))
            output = io.BytesIO()
            img.save(output, format="PNG")
            return output.getvalue()
        except Exception as e:
            logger.error(f"Failed to convert DIB to bytes: {e}")
            return None

    def read_files(self) -> list[str] | None:
        if self._ensure_initialized():
            return self._read_files_win32()
        return self._read_files_powershell()

    def _read_files_win32(self) -> list[str] | None:
        try:
            self._win32clipboard.OpenClipboard()
            try:
                format_id = 49159
                if self._win32clipboard.IsClipboardFormatAvailable(format_id):
                    data = self._win32clipboard.GetClipboardData(format_id)
                    return self._parse_file_list(data)
            finally:
                self._win32clipboard.CloseClipboard()
        except Exception as e:
            logger.error(f"Failed to read files from clipboard (win32): {e}")
        return None

    def _read_files_powershell(self) -> list[str] | None:
        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-command",
                    "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Clipboard]::GetFileDropList() | ForEach-Object { $_ }",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
                return files
        except Exception as e:
            logger.error(f"Failed to read files from clipboard (powershell): {e}")
        return None

    def _parse_file_list(self, data: bytes) -> list[str]:
        files = []
        try:
            decoded = data.decode("utf-16-le", errors="replace")
            parts = decoded.split("\x00")
            for part in parts:
                part = part.strip()
                if part:
                    files.append(part)
        except Exception as e:
            logger.error(f"Failed to parse file list: {e}")
        return files

    def has_content(self) -> bool:
        if self._ensure_initialized():
            try:
                self._win32clipboard.OpenClipboard()
                try:
                    return self._win32clipboard.CountClipboardFormats() > 0
                finally:
                    self._win32clipboard.CloseClipboard()
            except Exception:
                pass
        return self._has_content_powershell()

    def _has_content_powershell(self) -> bool:
        try:
            result = subprocess.run(
                ["powershell", "-command", "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Clipboard]::ContainsText()"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0 and result.stdout.strip().lower() == "true"
        except Exception:
            return False


class MacOSClipboardBackend:
    def read_text(self) -> str | None:
        try:
            result = subprocess.run(
                ["pbpaste"],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.decode("utf-8", errors="replace")
        except Exception as e:
            logger.error(f"Failed to read text from clipboard (pbpaste): {e}")
        return None

    def read_image(self) -> bytes | None:
        try:
            result = subprocess.run(
                ["pngpaste", "-"],
                capture_output=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout
        except FileNotFoundError:
            logger.warning("pngpaste not installed, trying osascript")
            return self._read_image_osascript()
        except Exception as e:
            logger.error(f"Failed to read image from clipboard: {e}")
        return None

    def _read_image_osascript(self) -> bytes | None:
        try:
            script = '''
            tell application "System Events"
                try
                    set theData to the clipboard as «class PNGf»
                    return theData
                end try
            end tell
            '''
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout
        except Exception as e:
            logger.error(f"Failed to read image via osascript: {e}")
        return None

    def read_files(self) -> list[str] | None:
        try:
            script = '''
            tell application "Finder"
                set theFiles to {}
                try
                    set theClipboard to the clipboard as «class furl»
                    set end of theFiles to POSIX path of theClipboard
                end try
                return theFiles
            end tell
            '''
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                return [result.stdout.strip()]
        except Exception as e:
            logger.error(f"Failed to read files from clipboard: {e}")
        return None

    def has_content(self) -> bool:
        try:
            result = subprocess.run(
                ["pbpaste"],
                capture_output=True,
                timeout=2,
            )
            return result.returncode == 0
        except Exception:
            return False


class LinuxClipboardBackend:
    def __init__(self):
        self._backend = self._detect_backend()

    def _detect_backend(self) -> str:
        for cmd in ["wl-copy", "xclip", "xsel"]:
            try:
                subprocess.run(
                    ["which", cmd],
                    capture_output=True,
                    check=True,
                )
                if cmd == "wl-copy":
                    return "wayland"
                elif cmd == "xclip":
                    return "xclip"
                elif cmd == "xsel":
                    return "xsel"
            except subprocess.CalledProcessError:
                continue
        return "unknown"

    def read_text(self) -> str | None:
        if self._backend == "wayland":
            return self._read_text_wayland()
        elif self._backend == "xclip":
            return self._read_text_xclip()
        elif self._backend == "xsel":
            return self._read_text_xsel()
        return None

    def _read_text_wayland(self) -> str | None:
        try:
            result = subprocess.run(
                ["wl-paste", "--no-newline"],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.decode("utf-8", errors="replace")
        except Exception as e:
            logger.error(f"Failed to read text via wl-paste: {e}")
        return None

    def _read_text_xclip(self) -> str | None:
        try:
            result = subprocess.run(
                ["xclip", "-selection", "clipboard", "-o"],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.decode("utf-8", errors="replace")
        except Exception as e:
            logger.error(f"Failed to read text via xclip: {e}")
        return None

    def _read_text_xsel(self) -> str | None:
        try:
            result = subprocess.run(
                ["xsel", "--clipboard", "--output"],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.decode("utf-8", errors="replace")
        except Exception as e:
            logger.error(f"Failed to read text via xsel: {e}")
        return None

    def read_image(self) -> bytes | None:
        if self._backend == "wayland":
            return self._read_image_wayland()
        elif self._backend == "xclip":
            return self._read_image_xclip()
        return None

    def _read_image_wayland(self) -> bytes | None:
        try:
            result = subprocess.run(
                ["wl-paste", "--type", "image/png"],
                capture_output=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout
        except Exception as e:
            logger.error(f"Failed to read image via wl-paste: {e}")
        return None

    def _read_image_xclip(self) -> bytes | None:
        try:
            result = subprocess.run(
                ["xclip", "-selection", "clipboard", "-t", "image/png", "-o"],
                capture_output=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout
        except Exception as e:
            logger.error(f"Failed to read image via xclip: {e}")
        return None

    def read_files(self) -> list[str] | None:
        if self._backend == "wayland":
            return self._read_files_wayland()
        return None

    def _read_files_wayland(self) -> list[str] | None:
        try:
            result = subprocess.run(
                ["wl-paste", "--list-types"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if "text/uri-list" in result.stdout:
                file_result = subprocess.run(
                    ["wl-paste", "--type", "text/uri-list"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if file_result.returncode == 0:
                    files = []
                    for line in file_result.stdout.strip().split("\n"):
                        if line.startswith("file://"):
                            files.append(line[7:])
                    return files
        except Exception as e:
            logger.error(f"Failed to read files via wl-paste: {e}")
        return None

    def has_content(self) -> bool:
        return self.read_text() is not None


class ClipboardReader:
    def __init__(self, enable_history: bool = False, max_history: int = 100):
        self._backend = self._create_backend()
        self._history = ClipboardHistory(max_items=max_history) if enable_history else None
        self._enable_history = enable_history

    def _create_backend(self) -> WindowsClipboardBackend | MacOSClipboardBackend | LinuxClipboardBackend:
        if PlatformClipboard.is_windows():
            return WindowsClipboardBackend()
        elif PlatformClipboard.is_macos():
            return MacOSClipboardBackend()
        elif PlatformClipboard.is_linux():
            return LinuxClipboardBackend()
        else:
            raise RuntimeError(f"Unsupported platform: {platform.system()}")

    async def read_text(self) -> ExecutionResult:
        try:
            loop = asyncio.get_event_loop()
            text = await loop.run_in_executor(None, self._backend.read_text)

            if text is None:
                return ExecutionResult(
                    status=ExecutionStatus.FAILED,
                    action="clipboard_read_text",
                    error_code=ErrorCode.RESOURCE_NOT_FOUND,
                    error_message="No text content in clipboard",
                )

            content = ClipboardContent(
                content_type=ClipboardContentType.TEXT,
                data=text,
                metadata={"encoding": "utf-8"},
                size_bytes=len(text.encode("utf-8")),
            )

            if self._enable_history:
                self._add_to_history(content)

            return ExecutionResult(
                status=ExecutionStatus.SUCCESS,
                action="clipboard_read_text",
                output={"text": text, "size": content.size_bytes},
                metadata={"content_type": ClipboardContentType.TEXT.value},
            )
        except Exception as e:
            logger.error(f"Failed to read text from clipboard: {e}")
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                action="clipboard_read_text",
                error_code=ErrorCode.EXECUTION_ERROR,
                error_message=str(e),
            )

    async def read_image(self, output_format: str = "base64") -> ExecutionResult:
        try:
            loop = asyncio.get_event_loop()
            image_data = await loop.run_in_executor(None, self._backend.read_image)

            if image_data is None:
                return ExecutionResult(
                    status=ExecutionStatus.FAILED,
                    action="clipboard_read_image",
                    error_code=ErrorCode.RESOURCE_NOT_FOUND,
                    error_message="No image content in clipboard",
                )

            if output_format == "base64":
                output_data = base64.b64encode(image_data).decode("utf-8")
            else:
                output_data = image_data

            content = ClipboardContent(
                content_type=ClipboardContentType.IMAGE,
                data=output_data,
                metadata={"format": "png", "output_format": output_format},
                size_bytes=len(image_data),
            )

            if self._enable_history:
                self._add_to_history(content)

            return ExecutionResult(
                status=ExecutionStatus.SUCCESS,
                action="clipboard_read_image",
                output={
                    "image": output_data,
                    "size": content.size_bytes,
                    "format": "png",
                },
                metadata={"content_type": ClipboardContentType.IMAGE.value},
            )
        except Exception as e:
            logger.error(f"Failed to read image from clipboard: {e}")
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                action="clipboard_read_image",
                error_code=ErrorCode.EXECUTION_ERROR,
                error_message=str(e),
            )

    async def read_files(self) -> ExecutionResult:
        try:
            loop = asyncio.get_event_loop()
            files = await loop.run_in_executor(None, self._backend.read_files)

            if files is None or len(files) == 0:
                return ExecutionResult(
                    status=ExecutionStatus.FAILED,
                    action="clipboard_read_files",
                    error_code=ErrorCode.RESOURCE_NOT_FOUND,
                    error_message="No files in clipboard",
                )

            valid_files = []
            for file_path in files:
                path = Path(file_path)
                if path.exists():
                    valid_files.append({
                        "path": str(path),
                        "name": path.name,
                        "is_dir": path.is_dir(),
                        "size": path.stat().st_size if path.is_file() else 0,
                    })

            content = ClipboardContent(
                content_type=ClipboardContentType.FILES,
                data=valid_files,
                metadata={"count": len(valid_files)},
                size_bytes=sum(f["size"] for f in valid_files),
            )

            if self._enable_history:
                self._add_to_history(content)

            return ExecutionResult(
                status=ExecutionStatus.SUCCESS,
                action="clipboard_read_files",
                output={"files": valid_files, "count": len(valid_files)},
                metadata={"content_type": ClipboardContentType.FILES.value},
            )
        except Exception as e:
            logger.error(f"Failed to read files from clipboard: {e}")
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                action="clipboard_read_files",
                error_code=ErrorCode.EXECUTION_ERROR,
                error_message=str(e),
            )

    async def read_auto(self) -> ExecutionResult:
        try:
            text_result = await self.read_text()
            if text_result.status == ExecutionStatus.SUCCESS:
                return text_result

            image_result = await self.read_image()
            if image_result.status == ExecutionStatus.SUCCESS:
                return image_result

            files_result = await self.read_files()
            if files_result.status == ExecutionStatus.SUCCESS:
                return files_result

            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                action="clipboard_read_auto",
                error_code=ErrorCode.RESOURCE_NOT_FOUND,
                error_message="No content in clipboard",
            )
        except Exception as e:
            logger.error(f"Failed to auto-read clipboard: {e}")
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                action="clipboard_read_auto",
                error_code=ErrorCode.EXECUTION_ERROR,
                error_message=str(e),
            )

    async def detect_content_type(self) -> ClipboardContentType:
        try:
            text = await asyncio.get_event_loop().run_in_executor(
                None, self._backend.read_text
            )
            if text:
                return ClipboardContentType.TEXT

            image = await asyncio.get_event_loop().run_in_executor(
                None, self._backend.read_image
            )
            if image:
                return ClipboardContentType.IMAGE

            files = await asyncio.get_event_loop().run_in_executor(
                None, self._backend.read_files
            )
            if files:
                return ClipboardContentType.FILES

            return ClipboardContentType.UNKNOWN
        except Exception:
            return ClipboardContentType.UNKNOWN

    async def has_content(self) -> bool:
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._backend.has_content)
        except Exception:
            return False

    def _add_to_history(self, content: ClipboardContent) -> None:
        if self._history is None:
            return

        self._history.items.append(content)
        self._history.current_index = len(self._history.items) - 1

        if len(self._history.items) > self._history.max_items:
            self._history.items = self._history.items[-self._history.max_items :]

    def get_history(self) -> list[dict[str, Any]]:
        if self._history is None:
            return []

        return [
            {
                "content_type": item.content_type.value,
                "size_bytes": item.size_bytes,
                "metadata": item.metadata,
                "preview": self._get_preview(item),
            }
            for item in self._history.items
        ]

    def _get_preview(self, content: ClipboardContent) -> str:
        if content.content_type == ClipboardContentType.TEXT:
            text = content.data
            if len(text) > 100:
                return text[:100] + "..."
            return text
        elif content.content_type == ClipboardContentType.IMAGE:
            return f"[Image: {content.size_bytes} bytes]"
        elif content.content_type == ClipboardContentType.FILES:
            return f"[{len(content.data)} files]"
        return "[Unknown content]"

    def clear_history(self) -> None:
        if self._history is not None:
            self._history.items.clear()
            self._history.current_index = -1

    def get_platform_info(self) -> dict[str, Any]:
        return {
            "platform": PlatformClipboard.get_platform(),
            "is_windows": PlatformClipboard.is_windows(),
            "is_macos": PlatformClipboard.is_macos(),
            "is_linux": PlatformClipboard.is_linux(),
            "history_enabled": self._enable_history,
            "history_count": len(self._history.items) if self._history else 0,
        }
