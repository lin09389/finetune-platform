import asyncio
import base64
import io
import logging
import platform
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from agent.core.types import ErrorCode, ExecutionResult, ExecutionStatus

logger = logging.getLogger(__name__)


class WindowsClipboardWriter:
    def __init__(self):
        self._win32clipboard = None
        self._win32con = None
        self._initialized = False

    def _ensure_initialized(self) -> bool:
        if self._initialized:
            return True

        try:
            import win32clipboard
            import win32con
            self._win32clipboard = win32clipboard
            self._win32con = win32con
            self._initialized = True
            return True
        except ImportError:
            logger.warning("pywin32 not available, using subprocess fallback")
            return False

    def write_text(self, text: str) -> bool:
        if self._ensure_initialized():
            return self._write_text_win32(text)
        return self._write_text_powershell(text)

    def _write_text_win32(self, text: str) -> bool:
        try:
            self._win32clipboard.OpenClipboard()
            try:
                self._win32clipboard.EmptyClipboard()
                self._win32clipboard.SetClipboardText(text, self._win32con.CF_UNICODETEXT)
                return True
            finally:
                self._win32clipboard.CloseClipboard()
        except Exception as e:
            logger.error(f"Failed to write text to clipboard (win32): {e}")
            return False

    def _write_text_powershell(self, text: str) -> bool:
        try:
            escaped_text = text.replace("'", "''")
            result = subprocess.run(
                ["powershell", "-command", f"Set-Clipboard -Value '{escaped_text}'"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Failed to write text to clipboard (powershell): {e}")
            return False

    def write_image(self, image_data: bytes) -> bool:
        if self._ensure_initialized():
            return self._write_image_win32(image_data)
        return self._write_image_powershell(image_data)

    def _write_image_win32(self, image_data: bytes) -> bool:
        try:
            from PIL import Image

            img = Image.open(io.BytesIO(image_data))

            if img.mode != "RGB":
                img = img.convert("RGB")

            output = io.BytesIO()
            img.save(output, format="BMP")
            bmp_data = output.getvalue()

            bmp_header_offset = 14
            dib_data = bmp_data[bmp_header_offset:]

            self._win32clipboard.OpenClipboard()
            try:
                self._win32clipboard.EmptyClipboard()
                self._win32clipboard.SetClipboardData(self._win32con.CF_DIB, dib_data)
                return True
            finally:
                self._win32clipboard.CloseClipboard()
        except ImportError:
            logger.warning("PIL not available for image conversion")
            return False
        except Exception as e:
            logger.error(f"Failed to write image to clipboard (win32): {e}")
            return False

    def _write_image_powershell(self, image_data: bytes) -> bool:
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                f.write(image_data)
                temp_path = f.name

            try:
                result = subprocess.run(
                    [
                        "powershell",
                        "-command",
                        f"Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Clipboard]::SetImage([System.Drawing.Image]::FromFile('{temp_path}'))",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                return result.returncode == 0
            finally:
                Path(temp_path).unlink(missing_ok=True)
        except Exception as e:
            logger.error(f"Failed to write image to clipboard (powershell): {e}")
            return False

    def write_files(self, file_paths: list[str]) -> bool:
        if self._ensure_initialized():
            return self._write_files_win32(file_paths)
        return self._write_files_powershell(file_paths)

    def _write_files_win32(self, file_paths: list[str]) -> bool:
        try:
            import struct

            self._win32clipboard.OpenClipboard()
            try:
                self._win32clipboard.EmptyClipboard()

                data = struct.pack("I", 0)
                for path in file_paths:
                    wide_path = path.encode("utf-16-le") + b"\x00\x00"
                    data += struct.pack("I", len(wide_path)) + wide_path
                data += b"\x00\x00"

                format_id = 49159
                self._win32clipboard.SetClipboardData(format_id, data)
                return True
            finally:
                self._win32clipboard.CloseClipboard()
        except Exception as e:
            logger.error(f"Failed to write files to clipboard (win32): {e}")
            return False

    def _write_files_powershell(self, file_paths: list[str]) -> bool:
        try:
            paths_str = ",".join(f"'{p}'" for p in file_paths)
            result = subprocess.run(
                [
                    "powershell",
                    "-command",
                    f"Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Clipboard]::SetFileDropList(@({paths_str}))",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Failed to write files to clipboard (powershell): {e}")
            return False

    def clear(self) -> bool:
        if self._ensure_initialized():
            try:
                self._win32clipboard.OpenClipboard()
                try:
                    self._win32clipboard.EmptyClipboard()
                    return True
                finally:
                    self._win32clipboard.CloseClipboard()
            except Exception as e:
                logger.error(f"Failed to clear clipboard (win32): {e}")
                return False
        return self._clear_powershell()

    def _clear_powershell(self) -> bool:
        try:
            result = subprocess.run(
                ["powershell", "-command", "Set-Clipboard -Value ''"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Failed to clear clipboard (powershell): {e}")
            return False


class MacOSClipboardWriter:
    def write_text(self, text: str) -> bool:
        try:
            process = subprocess.Popen(
                ["pbcopy"],
                stdin=subprocess.PIPE,
            )
            process.communicate(input=text.encode("utf-8"))
            return process.returncode == 0
        except Exception as e:
            logger.error(f"Failed to write text to clipboard (pbcopy): {e}")
            return False

    def write_image(self, image_data: bytes) -> bool:
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                f.write(image_data)
                temp_path = f.name

            try:
                result = subprocess.run(
                    ["osascript", "-e", f'set the clipboard to (read (POSIX file "{temp_path}") as «class PNGf»)'],
                    capture_output=True,
                    timeout=10,
                )
                return result.returncode == 0
            finally:
                Path(temp_path).unlink(missing_ok=True)
        except Exception as e:
            logger.error(f"Failed to write image to clipboard: {e}")
            return False

    def write_files(self, file_paths: list[str]) -> bool:
        try:
            script = '''
            tell application "Finder"
                set theFiles to {}
            '''
            for path in file_paths:
                script += f'''
                set end of theFiles to POSIX file "{path}"
                '''
            script += '''
                set the clipboard to theFiles
            end tell
            '''
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Failed to write files to clipboard: {e}")
            return False

    def clear(self) -> bool:
        try:
            process = subprocess.Popen(
                ["pbcopy"],
                stdin=subprocess.PIPE,
            )
            process.communicate(input=b"")
            return process.returncode == 0
        except Exception as e:
            logger.error(f"Failed to clear clipboard: {e}")
            return False


class LinuxClipboardWriter:
    def __init__(self):
        self._backend = self._detect_backend()

    def _detect_backend(self) -> str:
        mapping = {
            "wl-copy": "wayland",
            "xclip": "xclip",
            "xsel": "xsel",
        }
        for cmd in ["wl-copy", "xclip", "xsel"]:
            try:
                subprocess.run(
                    ["which", cmd],
                    capture_output=True,
                    check=True,
                )
                return mapping[cmd]
            except subprocess.CalledProcessError:
                continue
        return "unknown"

    def write_text(self, text: str) -> bool:
        writers = {
            "wayland": self._write_text_wayland,
            "xclip": self._write_text_xclip,
            "xsel": self._write_text_xsel,
        }
        writer = writers.get(self._backend)
        return writer(text) if writer else False

    def _write_text_wayland(self, text: str) -> bool:
        try:
            process = subprocess.Popen(
                ["wl-copy"],
                stdin=subprocess.PIPE,
            )
            process.communicate(input=text.encode("utf-8"))
            return process.returncode == 0
        except Exception as e:
            logger.error(f"Failed to write text via wl-copy: {e}")
            return False

    def _write_text_xclip(self, text: str) -> bool:
        try:
            process = subprocess.Popen(
                ["xclip", "-selection", "clipboard"],
                stdin=subprocess.PIPE,
            )
            process.communicate(input=text.encode("utf-8"))
            return process.returncode == 0
        except Exception as e:
            logger.error(f"Failed to write text via xclip: {e}")
            return False

    def _write_text_xsel(self, text: str) -> bool:
        try:
            process = subprocess.Popen(
                ["xsel", "--clipboard", "--input"],
                stdin=subprocess.PIPE,
            )
            process.communicate(input=text.encode("utf-8"))
            return process.returncode == 0
        except Exception as e:
            logger.error(f"Failed to write text via xsel: {e}")
            return False

    def write_image(self, image_data: bytes) -> bool:
        if self._backend == "wayland":
            return self._write_image_wayland(image_data)
        elif self._backend == "xclip":
            return self._write_image_xclip(image_data)
        return False

    def _write_image_wayland(self, image_data: bytes) -> bool:
        try:
            process = subprocess.Popen(
                ["wl-copy", "--type", "image/png"],
                stdin=subprocess.PIPE,
            )
            process.communicate(input=image_data)
            return process.returncode == 0
        except Exception as e:
            logger.error(f"Failed to write image via wl-copy: {e}")
            return False

    def _write_image_xclip(self, image_data: bytes) -> bool:
        try:
            process = subprocess.Popen(
                ["xclip", "-selection", "clipboard", "-t", "image/png", "-i"],
                stdin=subprocess.PIPE,
            )
            process.communicate(input=image_data)
            return process.returncode == 0
        except Exception as e:
            logger.error(f"Failed to write image via xclip: {e}")
            return False

    def write_files(self, file_paths: list[str]) -> bool:
        if self._backend == "wayland":
            return self._write_files_wayland(file_paths)
        return False

    def _write_files_wayland(self, file_paths: list[str]) -> bool:
        try:
            uri_list = "\n".join(f"file://{path}" for path in file_paths)
            process = subprocess.Popen(
                ["wl-copy", "--type", "text/uri-list"],
                stdin=subprocess.PIPE,
            )
            process.communicate(input=uri_list.encode("utf-8"))
            return process.returncode == 0
        except Exception as e:
            logger.error(f"Failed to write files via wl-copy: {e}")
            return False

    def clear(self) -> bool:
        if self._backend == "wayland":
            try:
                subprocess.run(["wl-copy", "--clear"], check=True, timeout=5)
                return True
            except Exception as e:
                logger.error(f"Failed to clear clipboard via wl-copy: {e}")
                return False
        elif self._backend == "xclip":
            return self._write_text_xclip("")
        elif self._backend == "xsel":
            return self._write_text_xsel("")
        return False


class ClipboardWriter:
    def __init__(self):
        self._backend = self._create_backend()

    def _create_backend(self) -> WindowsClipboardWriter | MacOSClipboardWriter | LinuxClipboardWriter:
        system = platform.system().lower()
        if system == "windows":
            return WindowsClipboardWriter()
        elif system == "darwin":
            return MacOSClipboardWriter()
        elif system == "linux":
            return LinuxClipboardWriter()
        else:
            raise RuntimeError(f"Unsupported platform: {system}")

    async def write_text(self, text: str) -> ExecutionResult:
        if not isinstance(text, str):
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                action="clipboard_write_text",
                error_code=ErrorCode.VALIDATION_ERROR,
                error_message="Text must be a string",
            )

        try:
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(None, self._backend.write_text, text)

            if success:
                return ExecutionResult(
                    status=ExecutionStatus.SUCCESS,
                    action="clipboard_write_text",
                    output={"bytes_written": len(text.encode("utf-8"))},
                    metadata={"content_type": "text"},
                )
            else:
                return ExecutionResult(
                    status=ExecutionStatus.FAILED,
                    action="clipboard_write_text",
                    error_code=ErrorCode.EXECUTION_ERROR,
                    error_message="Failed to write text to clipboard",
                )
        except Exception as e:
            logger.error(f"Failed to write text to clipboard: {e}")
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                action="clipboard_write_text",
                error_code=ErrorCode.EXECUTION_ERROR,
                error_message=str(e),
            )

    async def write_image(
        self,
        image_data: bytes | str,
        input_format: str = "bytes",
    ) -> ExecutionResult:
        try:
            if input_format == "base64":
                if isinstance(image_data, str):
                    image_data = base64.b64decode(image_data)
                else:
                    return ExecutionResult(
                        status=ExecutionStatus.FAILED,
                        action="clipboard_write_image",
                        error_code=ErrorCode.VALIDATION_ERROR,
                        error_message="Base64 image must be a string",
                    )
            elif not isinstance(image_data, bytes):
                return ExecutionResult(
                    status=ExecutionStatus.FAILED,
                    action="clipboard_write_image",
                    error_code=ErrorCode.VALIDATION_ERROR,
                    error_message="Image data must be bytes or base64 string",
                )

            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(None, self._backend.write_image, image_data)

            if success:
                return ExecutionResult(
                    status=ExecutionStatus.SUCCESS,
                    action="clipboard_write_image",
                    output={"bytes_written": len(image_data)},
                    metadata={"content_type": "image", "format": "png"},
                )
            else:
                return ExecutionResult(
                    status=ExecutionStatus.FAILED,
                    action="clipboard_write_image",
                    error_code=ErrorCode.EXECUTION_ERROR,
                    error_message="Failed to write image to clipboard",
                )
        except Exception as e:
            logger.error(f"Failed to write image to clipboard: {e}")
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                action="clipboard_write_image",
                error_code=ErrorCode.EXECUTION_ERROR,
                error_message=str(e),
            )

    async def write_files(self, file_paths: list[str]) -> ExecutionResult:
        if not isinstance(file_paths, list):
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                action="clipboard_write_files",
                error_code=ErrorCode.VALIDATION_ERROR,
                error_message="File paths must be a list",
            )

        if len(file_paths) == 0:
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                action="clipboard_write_files",
                error_code=ErrorCode.VALIDATION_ERROR,
                error_message="File paths list cannot be empty",
            )

        valid_paths = []
        invalid_paths = []

        for path in file_paths:
            if not isinstance(path, str):
                invalid_paths.append(str(path))
                continue

            p = Path(path)
            if p.exists():
                valid_paths.append(str(p.absolute()))
            else:
                invalid_paths.append(path)

        if len(valid_paths) == 0:
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                action="clipboard_write_files",
                error_code=ErrorCode.RESOURCE_NOT_FOUND,
                error_message=f"No valid file paths found. Invalid: {invalid_paths}",
            )

        try:
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(None, self._backend.write_files, valid_paths)

            if success:
                return ExecutionResult(
                    status=ExecutionStatus.SUCCESS,
                    action="clipboard_write_files",
                    output={
                        "files_copied": len(valid_paths),
                        "files": valid_paths,
                    },
                    metadata={
                        "content_type": "files",
                        "invalid_paths": invalid_paths,
                    },
                )
            else:
                return ExecutionResult(
                    status=ExecutionStatus.FAILED,
                    action="clipboard_write_files",
                    error_code=ErrorCode.EXECUTION_ERROR,
                    error_message="Failed to write files to clipboard",
                )
        except Exception as e:
            logger.error(f"Failed to write files to clipboard: {e}")
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                action="clipboard_write_files",
                error_code=ErrorCode.EXECUTION_ERROR,
                error_message=str(e),
            )

    async def write_image_from_file(self, file_path: str) -> ExecutionResult:
        try:
            path = Path(file_path)
            if not path.exists():
                return ExecutionResult(
                    status=ExecutionStatus.FAILED,
                    action="clipboard_write_image_from_file",
                    error_code=ErrorCode.RESOURCE_NOT_FOUND,
                    error_message=f"File not found: {file_path}",
                )

            image_data = path.read_bytes()
            return await self.write_image(image_data, input_format="bytes")
        except Exception as e:
            logger.error(f"Failed to write image from file: {e}")
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                action="clipboard_write_image_from_file",
                error_code=ErrorCode.EXECUTION_ERROR,
                error_message=str(e),
            )

    async def clear(self) -> ExecutionResult:
        try:
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(None, self._backend.clear)

            if success:
                return ExecutionResult(
                    status=ExecutionStatus.SUCCESS,
                    action="clipboard_clear",
                    output={"cleared": True},
                )
            else:
                return ExecutionResult(
                    status=ExecutionStatus.FAILED,
                    action="clipboard_clear",
                    error_code=ErrorCode.EXECUTION_ERROR,
                    error_message="Failed to clear clipboard",
                )
        except Exception as e:
            logger.error(f"Failed to clear clipboard: {e}")
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                action="clipboard_clear",
                error_code=ErrorCode.EXECUTION_ERROR,
                error_message=str(e),
            )

    async def write_rich_text(
        self,
        text: str,
        html: str | None = None,
        rtf: str | None = None,
    ) -> ExecutionResult:
        try:
            success = await asyncio.get_event_loop().run_in_executor(
                None, self._backend.write_text, text
            )

            if success:
                metadata = {"content_type": "rich_text"}
                if html:
                    metadata["has_html"] = True
                if rtf:
                    metadata["has_rtf"] = True

                return ExecutionResult(
                    status=ExecutionStatus.SUCCESS,
                    action="clipboard_write_rich_text",
                    output={"bytes_written": len(text.encode("utf-8"))},
                    metadata=metadata,
                )
            else:
                return ExecutionResult(
                    status=ExecutionStatus.FAILED,
                    action="clipboard_write_rich_text",
                    error_code=ErrorCode.EXECUTION_ERROR,
                    error_message="Failed to write rich text to clipboard",
                )
        except Exception as e:
            logger.error(f"Failed to write rich text to clipboard: {e}")
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                action="clipboard_write_rich_text",
                error_code=ErrorCode.EXECUTION_ERROR,
                error_message=str(e),
            )

    def get_platform_info(self) -> dict[str, Any]:
        return {
            "platform": platform.system().lower(),
            "backend_type": type(self._backend).__name__,
        }
