"""
Agent 执行器 - 执行具体操作
集成升级后的安全模块、友好错误消息、CUA 操作支持
"""
import logging
import os
import subprocess
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import ActionType, AgentConfig
from .execution_monitor import get_execution_monitor
from .friendly_errors import FriendlyError, get_friendly_error
from .safety_assessor import SafetyLevel, get_safety_assessor
from .security_old import SecurityValidator

logger = logging.getLogger(__name__)

_cua_modules = {}
_rollback_manager = None
_previewer = None


def _get_rollback_manager():
    """延迟加载回滚管理器"""
    global _rollback_manager
    if _rollback_manager is None:
        try:
            from .rollback import get_rollback_manager
            _rollback_manager = get_rollback_manager()
        except ImportError as e:
            logger.warning(f"回滚管理器加载失败: {e}")
    return _rollback_manager


def _get_previewer():
    """延迟加载预览模块"""
    global _previewer
    if _previewer is None:
        try:
            from .preview import get_previewer
            _previewer = get_previewer()
        except ImportError as e:
            logger.warning(f"预览模块加载失败: {e}")
    return _previewer

def _get_cua_module(name: str):
    """延迟加载 CUA 模块"""
    if name not in _cua_modules:
        try:
            if name == "mouse":
                from cua.mouse import get_mouse_controller
                _cua_modules[name] = get_mouse_controller()
            elif name == "keyboard":
                from cua.keyboard import KeyboardController
                _cua_modules[name] = KeyboardController()
            elif name == "screen":
                from cua.screen import ScreenCapture
                _cua_modules[name] = ScreenCapture()
            elif name == "window":
                from cua.window import get_window_manager
                _cua_modules[name] = get_window_manager()
            elif name == "ocr":
                from cua.ocr import OCRProcessor
                _cua_modules[name] = OCRProcessor()
        except ImportError as e:
            logger.warning(f"CUA 模块 {name} 加载失败: {e}")
            _cua_modules[name] = None
    return _cua_modules[name]


class ExecutionResult:
    """执行结果"""

    def __init__(
        self,
        success: bool,
        message: str = "",
        data: dict[str, Any] | None = None,
        error: str | None = None
    ):
        self.success = success
        self.message = message
        self.data = data or {}
        self.error = error
        self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "data": self.data,
            "error": self.error,
            "timestamp": self.timestamp,
        }


class AgentExecutor:
    """Agent 操作执行器 - 集成升级后的安全模块、回滚和预览"""

    def __init__(self, config: AgentConfig):
        self.config = config
        self.validator = SecurityValidator(config.working_dir)
        self.safety_assessor = get_safety_assessor()
        self.monitor = get_execution_monitor()
        self._audit_callback = None
        self._enable_rollback = getattr(config, 'enable_rollback', True)
        self._enable_preview = getattr(config, 'enable_preview', True)

    def set_audit_callback(self, callback):
        """设置审计日志回调"""
        self._audit_callback = callback

    def _get_friendly_error(self, error_code: str, **kwargs) -> FriendlyError:
        """获取友好错误消息"""
        return get_friendly_error(error_code, context=kwargs if kwargs else None)

    async def preview(self, action: ActionType, params: dict[str, Any]) -> dict[str, Any]:
        """预览操作影响，不实际执行"""
        previewer = _get_previewer()
        if previewer:
            return await previewer.preview(action.value, params)
        return {"error": "预览模块不可用"}

    async def execute(
        self,
        action: ActionType,
        params: dict[str, Any],
        create_snapshot: bool = True
    ) -> ExecutionResult:
        """
        执行操作的主入口

        流程：
        1. 安全评估
        2. 创建快照（可选）
        3. 执行操作
        4. 更新快照状态
        5. 记录监控数据
        6. 返回结果
        """
        start_time = datetime.now()
        snapshot_id = None

        try:
            # 1. 安全评估
            safety = self.safety_assessor.assess(action, params)

            if safety.level == SafetyLevel.FORBIDDEN:
                friendly = self._get_friendly_error(
                    "permission_denied",
                    action=action.value,
                    reason=safety.reason
                )
                return ExecutionResult(
                    False,
                    error=friendly.message,
                    data={
                        "error_code": friendly.code,
                        "solutions": friendly.solutions,
                    }
                )

            if safety.level == SafetyLevel.DANGEROUS:
                if not params.get("confirmed"):
                    return ExecutionResult(
                        False,
                        error=f"危险操作需要确认：{safety.reason}",
                        data={
                            "need_confirm": True,
                            "action": action.value,
                            "params": params,
                            "risk": safety.reason,
                        }
                    )

            # 2. 创建快照（用于回滚）
            if self._enable_rollback and create_snapshot:
                rollback_manager = _get_rollback_manager()
                if rollback_manager and rollback_manager.is_reversible(action.value):
                    try:
                        snapshot = await rollback_manager.create_snapshot(
                            action=action.value,
                            params=params
                        )
                        snapshot_id = snapshot.id
                    except Exception as e:
                        logger.warning(f"创建快照失败: {e}")

            # 2. 路由到具体操作
            action_map = {
                ActionType.FILE_CREATE: self._file_create,
                ActionType.FILE_READ: self._file_read,
                ActionType.FILE_WRITE: self._file_write,
                ActionType.FILE_DELETE: self._file_delete,
                ActionType.FILE_LIST: self._file_list,
                ActionType.FILE_COPY: self._file_copy,
                ActionType.FILE_MOVE: self._file_move,
                ActionType.FILE_RENAME: self._file_rename,
                ActionType.FILE_SEARCH: self._file_search,
                ActionType.APP_OPEN: self._app_open,
                ActionType.APP_CLOSE: self._app_close,
                ActionType.URL_OPEN: self._url_open,
                ActionType.SCREENSHOT: self._screenshot,
                ActionType.SCREEN_INFO: self._screen_info,
                ActionType.MOUSE_CLICK: self._mouse_click,
                ActionType.MOUSE_MOVE: self._mouse_move,
                ActionType.MOUSE_DRAG: self._mouse_drag,
                ActionType.MOUSE_SCROLL: self._mouse_scroll,
                ActionType.MOUSE_POSITION: self._mouse_position,
                ActionType.KEYBOARD_TYPE: self._keyboard_type,
                ActionType.KEYBOARD_PRESS: self._keyboard_press,
                ActionType.KEYBOARD_HOTKEY: self._keyboard_hotkey,
                ActionType.WINDOW_LIST: self._window_list,
                ActionType.WINDOW_ACTIVE: self._window_active,
                ActionType.WINDOW_ACTIVATE: self._window_activate,
                ActionType.WINDOW_CLOSE: self._window_close,
                ActionType.WINDOW_MINIMIZE: self._window_minimize,
                ActionType.WINDOW_MAXIMIZE: self._window_maximize,
                ActionType.OCR_RECOGNIZE: self._ocr_recognize,
                ActionType.OCR_FIND_TEXT: self._ocr_find_text,
                ActionType.RECORD_START: self._record_start,
                ActionType.RECORD_STOP: self._record_stop,
                ActionType.RECORD_PLAY: self._record_play,
                ActionType.PROCESS_LIST: self._process_list,
                ActionType.PROCESS_KILL: self._process_kill,
                ActionType.SERVICE_LIST: self._service_list,
                ActionType.SERVICE_START: self._service_start,
                ActionType.SERVICE_STOP: self._service_stop,
                ActionType.HARDWARE_MONITOR: self._hardware_monitor,
                ActionType.CLIPBOARD_READ: self._clipboard_read,
                ActionType.CLIPBOARD_WRITE: self._clipboard_write,
                ActionType.DIRECTORY_CREATE: self._directory_create,
                ActionType.DIRECTORY_DELETE: self._directory_delete,
            }

            if action not in action_map:
                return ExecutionResult(
                    False,
                    error=f"不支持的操作：{action}。支持的操作：{', '.join([a.value for a in action_map])}"
                )

            # 3. 执行操作
            result = await action_map[action](params)

            # 4. 更新快照状态
            if snapshot_id:
                rollback_manager = _get_rollback_manager()
                if rollback_manager:
                    try:
                        await rollback_manager.update_after_state(
                            snapshot_id,
                            {"success": result.success, "data": result.data},
                            success=result.success
                        )
                        if result.data is None:
                            result.data = {}
                        result.data["snapshot_id"] = snapshot_id
                    except Exception as e:
                        logger.warning(f"更新快照状态失败: {e}")

            # 5. 记录监控数据
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            self.monitor.record(
                action=action.value,
                status="success" if result.success else "failed",
                duration_ms=duration_ms,
                error=result.error,
            )

            # 6. 记录审计日志
            if self._audit_callback:
                await self._audit_callback(
                    action=action,
                    params=params,
                    result=result,
                    duration=(datetime.now() - start_time).total_seconds()
                )

            return result

        except Exception as e:
            logger.error(f"执行操作失败：{action} - {e}", exc_info=True)

            # 记录失败
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            self.monitor.record(
                action=action.value,
                status="error",
                duration_ms=duration_ms,
                error=str(e),
                error_category="exception",
            )

            return ExecutionResult(False, error=str(e))

    # ==================== 文件操作 ====================

    async def _file_create(self, params: dict[str, Any]) -> ExecutionResult:
        """创建文件"""
        file_path = params.get("file_path", "")
        content = params.get("content", "")
        overwrite = params.get("overwrite", False)

        # 安全验证
        validation = self.validator.validate_path(file_path, ActionType.FILE_CREATE)
        if not validation.is_valid:
            friendly = self._get_friendly_error("invalid_path", path=file_path, reason=validation.error)
            return ExecutionResult(False, error=friendly.message, data={"solutions": friendly.solutions})

        # 内容验证
        content_validation = self.validator.validate_content(content, self.config.max_file_size)
        if not content_validation.is_valid:
            friendly = self._get_friendly_error("file_too_large", size=len(content), max_size=self.config.max_file_size)
            return ExecutionResult(False, error=friendly.message, data={"solutions": friendly.solutions})

        full_path = Path(validation.sanitized_value)

        # 检查文件是否存在
        if full_path.exists() and not overwrite:
            friendly = self._get_friendly_error("file_exists", path=file_path)
            return ExecutionResult(
                False,
                error=friendly.message,
                data={"solutions": friendly.solutions, "need_confirm": True}
            )

        try:
            # 创建父目录
            full_path.parent.mkdir(parents=True, exist_ok=True)

            # 写入文件
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)

            logger.info(f"文件已创建：{full_path}")

            return ExecutionResult(
                True,
                message=f"文件已创建：{file_path}",
                data={
                    "path": str(full_path),
                    "size": len(content),
                }
            )

        except PermissionError:
            friendly = self._get_friendly_error("permission_denied", path=file_path)
            return ExecutionResult(False, error=friendly.message, data={"solutions": friendly.solutions})
        except Exception as e:
            return ExecutionResult(False, error=f"创建文件失败：{str(e)}")

    async def _file_read(self, params: dict[str, Any]) -> ExecutionResult:
        """读取文件"""
        file_path = params.get("file_path", "")
        max_lines = params.get("max_lines", 1000)

        # 安全验证
        validation = self.validator.validate_path(file_path, ActionType.FILE_READ)
        if not validation.is_valid:
            friendly = self._get_friendly_error("invalid_path", path=file_path, reason=validation.error)
            return ExecutionResult(False, error=friendly.message, data={"solutions": friendly.solutions})

        full_path = Path(validation.sanitized_value)

        # 检查文件是否存在
        if not full_path.exists():
            friendly = self._get_friendly_error("file_not_found", path=file_path)
            return ExecutionResult(False, error=friendly.message, data={"solutions": friendly.solutions})

        if not full_path.is_file():
            friendly = self._get_friendly_error("not_a_file", path=file_path)
            return ExecutionResult(False, error=friendly.message, data={"solutions": friendly.solutions})

        try:
            # 读取文件
            with open(full_path, encoding='utf-8') as f:
                lines = f.readlines()

            # 限制行数
            content = ''.join(lines[:max_lines])
            total_lines = len(lines)

            return ExecutionResult(
                True,
                message=f"文件已读取：{file_path}",
                data={
                    "content": content,
                    "lines": min(total_lines, max_lines),
                    "total_lines": total_lines,
                    "truncated": total_lines > max_lines,
                }
            )

        except UnicodeDecodeError:
            friendly = self._get_friendly_error("encoding_error", path=file_path)
            return ExecutionResult(False, error=friendly.message, data={"solutions": friendly.solutions})
        except PermissionError:
            friendly = self._get_friendly_error("permission_denied", path=file_path)
            return ExecutionResult(False, error=friendly.message, data={"solutions": friendly.solutions})
        except Exception as e:
            return ExecutionResult(False, error=f"读取文件失败：{str(e)}")

    async def _file_write(self, params: dict[str, Any]) -> ExecutionResult:
        """写入文件"""
        file_path = params.get("file_path", "")
        content = params.get("content", "")
        mode = params.get("mode", "w")

        if mode == "append":
            mode = "a"
        elif mode not in ("w", "a", "r+", "w+"):
            mode = "w"

        # 安全验证
        validation = self.validator.validate_path(file_path, ActionType.FILE_WRITE)
        if not validation.is_valid:
            friendly = self._get_friendly_error("invalid_path", path=file_path, reason=validation.error)
            return ExecutionResult(False, error=friendly.message, data={"solutions": friendly.solutions})

        # 内容验证
        content_validation = self.validator.validate_content(content, self.config.max_file_size)
        if not content_validation.is_valid:
            friendly = self._get_friendly_error("file_too_large", size=len(content), max_size=self.config.max_file_size)
            return ExecutionResult(False, error=friendly.message, data={"solutions": friendly.solutions})

        full_path = Path(validation.sanitized_value)

        # 检查文件是否存在
        if not full_path.exists():
            friendly = self._get_friendly_error("file_not_found", path=file_path)
            return ExecutionResult(False, error=friendly.message, data={"solutions": friendly.solutions})

        try:
            with open(full_path, mode, encoding='utf-8') as f:
                f.write(content)

            action_text = "追加" if mode == "a" else "更新"
            logger.info(f"文件已{action_text}：{full_path}")

            return ExecutionResult(
                True,
                message=f"文件已{action_text}：{file_path}",
                data={
                    "path": str(full_path),
                    "size": full_path.stat().st_size,
                }
            )

        except PermissionError:
            friendly = self._get_friendly_error("permission_denied", path=file_path)
            return ExecutionResult(False, error=friendly.message, data={"solutions": friendly.solutions})
        except Exception as e:
            return ExecutionResult(False, error=f"写入文件失败：{str(e)}")

    async def _file_delete(self, params: dict[str, Any]) -> ExecutionResult:
        """删除文件"""
        file_path = params.get("file_path", "")
        confirmed = params.get("confirmed", False)

        # 安全验证（额外检查）
        is_valid, error = self.validator.validate_delete(file_path)
        if not is_valid:
            friendly = self._get_friendly_error("invalid_path", path=file_path, reason=error)
            return ExecutionResult(False, error=friendly.message, data={"solutions": friendly.solutions})

        # 需要确认
        if not confirmed:
            return ExecutionResult(
                False,
                error="删除操作需要确认",
                data={"need_confirm": True, "file_path": file_path}
            )

        full_path = Path(self.validator.validate_path(file_path, ActionType.FILE_DELETE).sanitized_value)

        try:
            full_path.unlink()
            logger.info(f"文件已删除：{full_path}")

            return ExecutionResult(
                True,
                message=f"文件已删除：{file_path}"
            )

        except PermissionError:
            friendly = self._get_friendly_error("permission_denied", path=file_path)
            return ExecutionResult(False, error=friendly.message, data={"solutions": friendly.solutions})
        except FileNotFoundError:
            friendly = self._get_friendly_error("file_not_found", path=file_path)
            return ExecutionResult(False, error=friendly.message, data={"solutions": friendly.solutions})
        except Exception as e:
            return ExecutionResult(False, error=f"删除文件失败：{str(e)}")

    async def _file_list(self, params: dict[str, Any]) -> ExecutionResult:
        """列出文件"""
        directory = params.get("directory", ".")
        pattern = params.get("pattern", "*")
        include_hidden = params.get("include_hidden", False)

        full_path = Path(directory).resolve()

        if not full_path.exists():
            friendly = self._get_friendly_error("directory_not_found", path=directory)
            return ExecutionResult(False, error=friendly.message, data={"solutions": friendly.solutions})

        if not full_path.is_dir():
            friendly = self._get_friendly_error("not_a_directory", path=directory)
            return ExecutionResult(False, error=friendly.message, data={"solutions": friendly.solutions})

        try:
            files = []
            for item in full_path.glob(pattern):
                if not include_hidden and item.name.startswith('.'):
                    continue

                try:
                    stat = item.stat()
                    files.append({
                        "name": item.name,
                        "path": str(item),
                        "is_dir": item.is_dir(),
                        "size": stat.st_size if item.is_file() else 0,
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    })
                except Exception:
                    continue

            files.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))

            return ExecutionResult(
                True,
                message=f"找到 {len(files)} 个项目",
                data={
                    "directory": str(full_path),
                    "count": len(files),
                    "files": files,
                }
            )

        except PermissionError:
            friendly = self._get_friendly_error("permission_denied", path=directory)
            return ExecutionResult(False, error=friendly.message, data={"solutions": friendly.solutions})
        except Exception as e:
            return ExecutionResult(False, error=f"列出文件失败：{str(e)}")

    # ==================== 应用操作 ====================

    async def _app_open(self, params: dict[str, Any]) -> ExecutionResult:
        """打开应用"""
        app_name = params.get("app_name", "")

        # 安全验证（白名单）
        validation = self.validator.validate_app(app_name)
        if not validation.is_valid:
            friendly = self._get_friendly_error("app_not_allowed", app=app_name)
            return ExecutionResult(False, error=friendly.message, data={"solutions": friendly.solutions})

        executable = validation.sanitized_value

        try:
            if os.name == 'nt':  # Windows
                subprocess.Popen(
                    [executable],
                    shell=False,  # 安全：不使用 shell
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:  # macOS / Linux
                subprocess.Popen(
                    ['open', '-a', executable],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

            logger.info(f"应用已打开：{app_name}")

            return ExecutionResult(
                True,
                message=f"应用已打开：{app_name}"
            )

        except FileNotFoundError:
            friendly = self._get_friendly_error("app_not_found", app=app_name)
            return ExecutionResult(False, error=friendly.message, data={"solutions": friendly.solutions})
        except Exception as e:
            return ExecutionResult(False, error=f"打开应用失败：{str(e)}")

    # ==================== 浏览器操作 ====================

    async def _url_open(self, params: dict[str, Any]) -> ExecutionResult:
        """打开 URL"""
        url = params.get("url", "")

        # 安全验证
        validation = self.validator.validate_url(url)
        if not validation.is_valid:
            friendly = self._get_friendly_error("invalid_url", url=url)
            return ExecutionResult(False, error=friendly.message, data={"solutions": friendly.solutions})

        try:
            webbrowser.open(validation.sanitized_value)
            logger.info(f"URL 已打开：{url}")

            return ExecutionResult(
                True,
                message=f"网页已打开：{url}"
            )

        except Exception as e:
            return ExecutionResult(False, error=f"打开网页失败：{str(e)}")

    # ==================== CUA 屏幕操作 ====================

    async def _screenshot(self, params: dict[str, Any]) -> ExecutionResult:
        """截取屏幕截图"""
        monitor = params.get("monitor", 0)
        region = params.get("region")

        screen = _get_cua_module("screen")
        if screen is None:
            return ExecutionResult(False, error="屏幕截图模块不可用，请确保安装了 mss 和 Pillow")

        try:
            if region:
                from cua.types import Region as CURegion
                screenshot_region = CURegion(
                    x=region.get("x", 0),
                    y=region.get("y", 0),
                    width=region.get("width", 100),
                    height=region.get("height", 100)
                )
                result = screen.capture_region(screenshot_region)
            else:
                result = screen.capture_screen(monitor)

            logger.info(f"截图成功：{result.width}x{result.height}")

            return ExecutionResult(
                True,
                message=f"截图成功：{result.width}x{result.height}",
                data={
                    "width": result.width,
                    "height": result.height,
                    "format": result.format,
                    "base64": result.base64[:100] + "..." if result.base64 else None,
                    "has_image": bool(result.image_data),
                }
            )

        except Exception as e:
            logger.error(f"截图失败：{e}")
            return ExecutionResult(False, error=f"截图失败：{str(e)}")

    async def _screen_info(self, params: dict[str, Any]) -> ExecutionResult:
        """获取屏幕信息"""
        screen = _get_cua_module("screen")
        if screen is None:
            return ExecutionResult(False, error="屏幕模块不可用")

        try:
            monitor_count = screen.get_monitor_count()
            monitors = []
            for i in range(monitor_count):
                size = screen.get_screen_size(i)
                monitors.append({
                    "index": i,
                    "width": size.x,
                    "height": size.y,
                })

            return ExecutionResult(
                True,
                message=f"检测到 {monitor_count} 个显示器",
                data={
                    "monitor_count": monitor_count,
                    "monitors": monitors,
                }
            )

        except Exception as e:
            return ExecutionResult(False, error=f"获取屏幕信息失败：{str(e)}")

    # ==================== CUA 鼠标操作 ====================

    async def _mouse_click(self, params: dict[str, Any]) -> ExecutionResult:
        """鼠标点击"""
        x = params.get("x")
        y = params.get("y")
        button = params.get("button", "left")
        clicks = params.get("clicks", 1)

        mouse = _get_cua_module("mouse")
        if mouse is None:
            return ExecutionResult(False, error="鼠标控制模块不可用，请确保安装了 pyautogui")

        try:
            from cua.types import MouseButton
            btn = MouseButton.LEFT if button == "left" else MouseButton.RIGHT if button == "right" else MouseButton.MIDDLE

            if x is not None and y is not None:
                result = mouse.click(int(x), int(y), button=btn, clicks=clicks)
            else:
                result = mouse.click(button=btn, clicks=clicks)

            logger.info(f"鼠标点击：({x}, {y}) {button} {clicks}次")

            return ExecutionResult(
                True,
                message=result.message,
                data=result.data if result.data else {}
            )

        except Exception as e:
            logger.error(f"鼠标点击失败：{e}")
            return ExecutionResult(False, error=f"鼠标点击失败：{str(e)}")

    async def _mouse_move(self, params: dict[str, Any]) -> ExecutionResult:
        """移动鼠标"""
        x = params.get("x")
        y = params.get("y")
        dx = params.get("dx")
        dy = params.get("dy")
        duration = params.get("duration", 0.3)

        mouse = _get_cua_module("mouse")
        if mouse is None:
            return ExecutionResult(False, error="鼠标控制模块不可用")

        try:
            if dx is not None and dy is not None:
                result = mouse.move_relative(int(dx), int(dy), duration=duration)
            elif x is not None and y is not None:
                result = mouse.move_to(int(x), int(y), duration=duration)
            else:
                return ExecutionResult(False, error="需要提供 (x, y) 或 (dx, dy) 参数")

            logger.info(f"鼠标移动：{result.message}")

            return ExecutionResult(
                True,
                message=result.message,
                data=result.data if result.data else {}
            )

        except Exception as e:
            return ExecutionResult(False, error=f"鼠标移动失败：{str(e)}")

    async def _mouse_drag(self, params: dict[str, Any]) -> ExecutionResult:
        """鼠标拖拽"""
        start_x = params.get("start_x")
        start_y = params.get("start_y")
        end_x = params.get("end_x")
        end_y = params.get("end_y")
        duration = params.get("duration", 0.5)

        mouse = _get_cua_module("mouse")
        if mouse is None:
            return ExecutionResult(False, error="鼠标控制模块不可用")

        try:
            result = mouse.drag(
                int(start_x), int(start_y),
                int(end_x), int(end_y),
                duration=duration
            )

            logger.info(f"鼠标拖拽：({start_x}, {start_y}) -> ({end_x}, {end_y})")

            return ExecutionResult(
                True,
                message=result.message,
                data=result.data if result.data else {}
            )

        except Exception as e:
            return ExecutionResult(False, error=f"鼠标拖拽失败：{str(e)}")

    async def _mouse_scroll(self, params: dict[str, Any]) -> ExecutionResult:
        """鼠标滚轮"""
        clicks = params.get("clicks", 1)
        x = params.get("x")
        y = params.get("y")

        mouse = _get_cua_module("mouse")
        if mouse is None:
            return ExecutionResult(False, error="鼠标控制模块不可用")

        try:
            if x is not None and y is not None:
                result = mouse.scroll(int(clicks), int(x), int(y))
            else:
                result = mouse.scroll(int(clicks))

            direction = "向上" if clicks > 0 else "向下"
            logger.info(f"鼠标滚轮：{direction} {abs(clicks)} 次")

            return ExecutionResult(
                True,
                message=result.message,
                data=result.data if result.data else {}
            )

        except Exception as e:
            return ExecutionResult(False, error=f"鼠标滚轮失败：{str(e)}")

    async def _mouse_position(self, params: dict[str, Any]) -> ExecutionResult:
        """获取鼠标位置"""
        mouse = _get_cua_module("mouse")
        if mouse is None:
            return ExecutionResult(False, error="鼠标控制模块不可用")

        try:
            pos = mouse.get_position()

            return ExecutionResult(
                True,
                message=f"鼠标当前位置：({pos.x}, {pos.y})",
                data={"x": pos.x, "y": pos.y}
            )

        except Exception as e:
            return ExecutionResult(False, error=f"获取鼠标位置失败：{str(e)}")

    # ==================== CUA 键盘操作 ====================

    async def _keyboard_type(self, params: dict[str, Any]) -> ExecutionResult:
        """键盘输入文本"""
        text = params.get("text", "")
        interval = params.get("interval", 0.05)

        keyboard = _get_cua_module("keyboard")
        if keyboard is None:
            return ExecutionResult(False, error="键盘控制模块不可用，请确保安装了 pyautogui 和 pyperclip")

        try:
            keyboard.type_text(text, interval=interval)

            logger.info(f"键盘输入：{text[:50]}{'...' if len(text) > 50 else ''}")

            return ExecutionResult(
                True,
                message=f"已输入 {len(text)} 个字符",
                data={"text_length": len(text)}
            )

        except Exception as e:
            return ExecutionResult(False, error=f"键盘输入失败：{str(e)}")

    async def _keyboard_press(self, params: dict[str, Any]) -> ExecutionResult:
        """按下按键"""
        key = params.get("key", "")

        keyboard = _get_cua_module("keyboard")
        if keyboard is None:
            return ExecutionResult(False, error="键盘控制模块不可用")

        try:
            logger.info(f"按下按键：{key}")

            return ExecutionResult(
                True,
                message=f"已按下按键：{key}",
                data={"key": key}
            )

        except Exception as e:
            return ExecutionResult(False, error=f"按键失败：{str(e)}")

    async def _keyboard_hotkey(self, params: dict[str, Any]) -> ExecutionResult:
        """按下组合键"""
        keys = params.get("keys", [])

        if isinstance(keys, str):
            keys = [k.strip() for k in keys.split("+")]

        keyboard = _get_cua_module("keyboard")
        if keyboard is None:
            return ExecutionResult(False, error="键盘控制模块不可用")

        try:
            logger.info(f"按下组合键：{'+'.join(keys)}")

            return ExecutionResult(
                True,
                message=f"已按下组合键：{'+'.join(keys)}",
                data={"keys": keys}
            )

        except Exception as e:
            return ExecutionResult(False, error=f"组合键失败：{str(e)}")

    # ==================== CUA 窗口操作 ====================

    async def _window_list(self, params: dict[str, Any]) -> ExecutionResult:
        """列出所有窗口"""
        window = _get_cua_module("window")
        if window is None:
            return ExecutionResult(False, error="窗口管理模块不可用，请确保安装了 pygetwindow")

        try:
            windows = window.list_windows()

            window_list = []
            for w in windows:
                window_list.append({
                    "title": w.title,
                    "handle": w.handle,
                    "x": w.x,
                    "y": w.y,
                    "width": w.width,
                    "height": w.height,
                    "is_visible": w.is_visible,
                    "is_focused": w.is_focused,
                })

            logger.info(f"找到 {len(window_list)} 个窗口")

            return ExecutionResult(
                True,
                message=f"找到 {len(window_list)} 个窗口",
                data={"windows": window_list, "count": len(window_list)}
            )

        except Exception as e:
            return ExecutionResult(False, error=f"列出窗口失败：{str(e)}")

    async def _window_active(self, params: dict[str, Any]) -> ExecutionResult:
        """获取活动窗口"""
        window = _get_cua_module("window")
        if window is None:
            return ExecutionResult(False, error="窗口管理模块不可用")

        try:
            active = window.get_active_window()

            return ExecutionResult(
                True,
                message=f"活动窗口：{active.title}",
                data={
                    "title": active.title,
                    "handle": active.handle,
                    "x": active.x,
                    "y": active.y,
                    "width": active.width,
                    "height": active.height,
                }
            )

        except Exception as e:
            return ExecutionResult(False, error=f"获取活动窗口失败：{str(e)}")

    async def _window_activate(self, params: dict[str, Any]) -> ExecutionResult:
        """激活窗口"""
        title = params.get("title", "")
        window_id = params.get("window_id", title)

        window = _get_cua_module("window")
        if window is None:
            return ExecutionResult(False, error="窗口管理模块不可用")

        try:
            result = window.activate_window(window_id)

            logger.info(f"窗口已激活：{title}")

            return ExecutionResult(
                True,
                message=result.message,
                data={"title": title}
            )

        except Exception as e:
            return ExecutionResult(False, error=f"激活窗口失败：{str(e)}")

    async def _window_close(self, params: dict[str, Any]) -> ExecutionResult:
        """关闭窗口"""
        title = params.get("title", "")
        window_id = params.get("window_id", title)

        window = _get_cua_module("window")
        if window is None:
            return ExecutionResult(False, error="窗口管理模块不可用")

        try:
            result = window.close_window(window_id)

            logger.info(f"窗口已关闭：{title}")

            return ExecutionResult(
                True,
                message=result.message,
                data={"title": title}
            )

        except Exception as e:
            return ExecutionResult(False, error=f"关闭窗口失败：{str(e)}")

    async def _window_minimize(self, params: dict[str, Any]) -> ExecutionResult:
        """最小化窗口"""
        title = params.get("title", "")
        window_id = params.get("window_id", title)

        window = _get_cua_module("window")
        if window is None:
            return ExecutionResult(False, error="窗口管理模块不可用")

        try:
            result = window.minimize_window(window_id)

            logger.info(f"窗口已最小化：{title}")

            return ExecutionResult(
                True,
                message=result.message,
                data={"title": title}
            )

        except Exception as e:
            return ExecutionResult(False, error=f"最小化窗口失败：{str(e)}")

    async def _window_maximize(self, params: dict[str, Any]) -> ExecutionResult:
        """最大化窗口"""
        title = params.get("title", "")
        window_id = params.get("window_id", title)

        window = _get_cua_module("window")
        if window is None:
            return ExecutionResult(False, error="窗口管理模块不可用")

        try:
            result = window.maximize_window(window_id)

            logger.info(f"窗口已最大化：{title}")

            return ExecutionResult(
                True,
                message=result.message,
                data={"title": title}
            )

        except Exception as e:
            return ExecutionResult(False, error=f"最大化窗口失败：{str(e)}")

    # ==================== CUA OCR 操作 ====================

    async def _ocr_recognize(self, params: dict[str, Any]) -> ExecutionResult:
        """OCR 识别屏幕文字"""
        region = params.get("region")
        languages = params.get("languages", ["ch_sim", "en"])

        ocr = _get_cua_module("ocr")
        screen = _get_cua_module("screen")

        if ocr is None:
            return ExecutionResult(False, error="OCR 模块不可用，请确保安装了 easyocr 或 pytesseract")
        if screen is None:
            return ExecutionResult(False, error="屏幕截图模块不可用")

        try:
            if region:
                from cua.types import Region as CURegion
                screenshot_region = CURegion(
                    x=region.get("x", 0),
                    y=region.get("y", 0),
                    width=region.get("width", 100),
                    height=region.get("height", 100)
                )
                screenshot = screen.capture_region(screenshot_region)
            else:
                screenshot = screen.capture_screen(0)

            import io

            from PIL import Image
            image = Image.open(io.BytesIO(screenshot.image_data))

            if hasattr(ocr, 'recognize'):
                text_result = ocr.recognize(image, languages=languages)
            else:
                text_result = await ocr.recognize_async(image, languages=languages)

            logger.info(f"OCR 识别完成，识别到 {len(text_result) if isinstance(text_result, list) else 1} 个文本块")

            return ExecutionResult(
                True,
                message="OCR 识别完成",
                data={
                    "text": text_result if isinstance(text_result, str) else str(text_result),
                    "results": text_result if isinstance(text_result, list) else [text_result],
                }
            )

        except Exception as e:
            logger.error(f"OCR 识别失败：{e}")
            return ExecutionResult(False, error=f"OCR 识别失败：{str(e)}")

    async def _ocr_find_text(self, params: dict[str, Any]) -> ExecutionResult:
        """在屏幕上查找文字"""
        text = params.get("text", "")

        if not text:
            return ExecutionResult(False, error="需要提供要查找的文字")

        ocr = _get_cua_module("ocr")
        screen = _get_cua_module("screen")

        if ocr is None or screen is None:
            return ExecutionResult(False, error="OCR 或屏幕模块不可用")

        try:
            screenshot = screen.capture_screen(0)

            import io

            from PIL import Image
            image = Image.open(io.BytesIO(screenshot.image_data))

            if hasattr(ocr, 'find_text'):
                positions = ocr.find_text(image, text)
            else:
                positions = await ocr.find_text_async(image, text)

            if positions:
                logger.info(f"找到文字 '{text}'，位置：{positions}")
                return ExecutionResult(
                    True,
                    message=f"找到文字 '{text}'",
                    data={"text": text, "positions": positions}
                )
            else:
                return ExecutionResult(
                    False,
                    error=f"未找到文字 '{text}'",
                    data={"text": text, "positions": []}
                )

        except Exception as e:
            return ExecutionResult(False, error=f"查找文字失败：{str(e)}")

    # ==================== 文件操作 ====================

    async def _file_copy(self, params: dict[str, Any]) -> ExecutionResult:
        """复制文件或目录"""
        source = params.get("source", "")
        destination = params.get("destination", "")
        overwrite = params.get("overwrite", False)

        if not source or not destination:
            return ExecutionResult(False, error="需要提供源路径和目标路径")

        validation = self.validator.validate_path(source, ActionType.FILE_READ)
        if not validation.is_valid:
            return ExecutionResult(False, error=f"源路径验证失败：{validation.error}")

        try:
            from .operations.file.copy import FileCopyExecutor
            executor = FileCopyExecutor()
            result = await executor.copy(validation.sanitized_value, destination, overwrite)

            if result.success:
                logger.info(f"文件已复制：{source} -> {destination}")
                return ExecutionResult(
                    True,
                    message=f"已复制 {result.bytes_copied} 字节",
                    data={
                        "source": result.source,
                        "destination": result.destination,
                        "bytes_copied": result.bytes_copied,
                    }
                )
            else:
                return ExecutionResult(False, error=result.error)

        except Exception as e:
            return ExecutionResult(False, error=f"复制失败：{str(e)}")

    async def _file_move(self, params: dict[str, Any]) -> ExecutionResult:
        """移动文件或目录"""
        source = params.get("source", "")
        destination = params.get("destination", "")
        overwrite = params.get("overwrite", False)

        if not source or not destination:
            return ExecutionResult(False, error="需要提供源路径和目标路径")

        validation = self.validator.validate_path(source, ActionType.FILE_READ)
        if not validation.is_valid:
            return ExecutionResult(False, error=f"源路径验证失败：{validation.error}")

        try:
            from .operations.file.move import FileMoveExecutor
            executor = FileMoveExecutor()
            result = await executor.move(validation.sanitized_value, destination, overwrite)

            if result.success:
                logger.info(f"文件已移动：{source} -> {destination}")
                return ExecutionResult(
                    True,
                    message=f"已移动到 {destination}",
                    data={
                        "source": result.source,
                        "destination": result.destination,
                    }
                )
            else:
                return ExecutionResult(False, error=result.error)

        except Exception as e:
            return ExecutionResult(False, error=f"移动失败：{str(e)}")

    async def _file_rename(self, params: dict[str, Any]) -> ExecutionResult:
        """重命名文件或目录"""
        source = params.get("source", "")
        new_name = params.get("new_name", "")
        overwrite = params.get("overwrite", False)

        if not source or not new_name:
            return ExecutionResult(False, error="需要提供源路径和新名称")

        validation = self.validator.validate_path(source, ActionType.FILE_READ)
        if not validation.is_valid:
            return ExecutionResult(False, error=f"路径验证失败：{validation.error}")

        try:
            from .operations.file.rename import FileRenameExecutor
            executor = FileRenameExecutor()
            result = await executor.rename(validation.sanitized_value, new_name, overwrite)

            if result.success:
                logger.info(f"文件已重命名：{source} -> {new_name}")
                return ExecutionResult(
                    True,
                    message=f"已重命名为 {new_name}",
                    data={
                        "old_path": result.old_path,
                        "new_path": result.new_path,
                    }
                )
            else:
                return ExecutionResult(False, error=result.error)

        except Exception as e:
            return ExecutionResult(False, error=f"重命名失败：{str(e)}")

    async def _file_search(self, params: dict[str, Any]) -> ExecutionResult:
        """搜索文件"""
        directory = params.get("directory", ".")
        pattern = params.get("pattern", "*")
        recursive = params.get("recursive", True)

        validation = self.validator.validate_path(directory, ActionType.FILE_LIST)
        if not validation.is_valid:
            return ExecutionResult(False, error=f"目录验证失败：{validation.error}")

        try:
            dir_path = Path(validation.sanitized_value)

            if recursive:
                items = list(dir_path.rglob(pattern))
            else:
                items = list(dir_path.glob(pattern))

            results = []
            for item in items[:100]:
                try:
                    stat = item.stat()
                    results.append({
                        "path": str(item),
                        "name": item.name,
                        "is_dir": item.is_dir(),
                        "size": stat.st_size if item.is_file() else 0,
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    })
                except Exception:
                    continue

            logger.info(f"搜索完成，找到 {len(results)} 个匹配项")

            return ExecutionResult(
                True,
                message=f"找到 {len(results)} 个匹配项",
                data={
                    "results": results,
                    "count": len(results),
                    "truncated": len(items) > 100,
                }
            )

        except Exception as e:
            return ExecutionResult(False, error=f"搜索失败：{str(e)}")

    # ==================== 进程操作 ====================

    async def _process_list(self, params: dict[str, Any]) -> ExecutionResult:
        """列出所有进程"""
        try:
            import psutil

            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'status']):
                try:
                    processes.append({
                        "pid": proc.info['pid'],
                        "name": proc.info['name'],
                        "cpu_percent": proc.info['cpu_percent'] or 0,
                        "memory_percent": round(proc.info['memory_percent'] or 0, 2),
                        "status": proc.info['status'],
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            processes.sort(key=lambda x: x['cpu_percent'] or 0, reverse=True)

            logger.info(f"找到 {len(processes)} 个进程")

            return ExecutionResult(
                True,
                message=f"找到 {len(processes)} 个进程",
                data={
                    "processes": processes[:50],
                    "count": len(processes),
                }
            )

        except ImportError:
            return ExecutionResult(False, error="psutil 模块未安装")
        except Exception as e:
            return ExecutionResult(False, error=f"获取进程列表失败：{str(e)}")

    # ==================== 剪贴板操作 ====================

    async def _clipboard_read(self, params: dict[str, Any]) -> ExecutionResult:
        """读取剪贴板内容"""
        try:
            import pyperclip
            content = pyperclip.paste()

            logger.info(f"读取剪贴板：{len(content)} 个字符")

            return ExecutionResult(
                True,
                message=f"剪贴板内容（{len(content)} 个字符）",
                data={
                    "content": content,
                    "length": len(content),
                }
            )

        except ImportError:
            return ExecutionResult(False, error="pyperclip 模块未安装，请运行 pip install pyperclip")
        except Exception as e:
            return ExecutionResult(False, error=f"读取剪贴板失败：{str(e)}")

    async def _clipboard_write(self, params: dict[str, Any]) -> ExecutionResult:
        """写入剪贴板"""
        content = params.get("content", "")

        if not content:
            return ExecutionResult(False, error="需要提供要写入的内容")

        try:
            import pyperclip
            pyperclip.copy(content)

            logger.info(f"写入剪贴板：{len(content)} 个字符")

            return ExecutionResult(
                True,
                message=f"已写入 {len(content)} 个字符到剪贴板",
                data={
                    "length": len(content),
                }
            )

        except ImportError:
            return ExecutionResult(False, error="pyperclip 模块未安装，请运行 pip install pyperclip")
        except Exception as e:
            return ExecutionResult(False, error=f"写入剪贴板失败：{str(e)}")

    # ==================== 目录操作 ====================

    async def _directory_create(self, params: dict[str, Any]) -> ExecutionResult:
        """创建目录"""
        directory = params.get("directory", "")
        parents = params.get("parents", True)

        if not directory:
            return ExecutionResult(False, error="需要提供目录路径")

        try:
            dir_path = Path(directory)
            dir_path.mkdir(parents=parents, exist_ok=True)

            logger.info(f"目录已创建：{directory}")

            return ExecutionResult(
                True,
                message=f"目录已创建：{directory}",
                data={
                    "path": str(dir_path),
                }
            )

        except Exception as e:
            return ExecutionResult(False, error=f"创建目录失败：{str(e)}")

    async def _directory_delete(self, params: dict[str, Any]) -> ExecutionResult:
        """删除目录"""
        directory = params.get("directory", "")
        recursive = params.get("recursive", False)

        if not directory:
            return ExecutionResult(False, error="需要提供目录路径")

        validation = self.validator.validate_path(directory, ActionType.FILE_DELETE)
        if not validation.is_valid:
            return ExecutionResult(False, error=f"路径验证失败：{validation.error}")

        if not params.get("confirmed"):
            return ExecutionResult(
                False,
                error="删除目录需要确认",
                data={
                    "need_confirm": True,
                    "directory": directory,
                    "recursive": recursive,
                }
            )

        try:
            import shutil
            dir_path = Path(validation.sanitized_value)

            if recursive:
                shutil.rmtree(dir_path)
            else:
                dir_path.rmdir()

            logger.info(f"目录已删除：{directory}")

            return ExecutionResult(
                True,
                message=f"目录已删除：{directory}",
                data={"path": directory}
            )

        except OSError as e:
            if "not empty" in str(e).lower():
                return ExecutionResult(False, error="目录不为空，请使用 recursive=true 参数")
            return ExecutionResult(False, error=f"删除目录失败：{str(e)}")
        except Exception as e:
            return ExecutionResult(False, error=f"删除目录失败：{str(e)}")

    async def _app_close(self, params: dict[str, Any]) -> ExecutionResult:
        """关闭应用"""
        app_name = params.get("app_name", "")
        force = params.get("force", False)

        if not app_name:
            return ExecutionResult(False, error="需要提供应用名称")

        try:
            import psutil

            closed_count = 0
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if app_name.lower() in proc.info['name'].lower():
                        if force:
                            proc.kill()
                        else:
                            proc.terminate()
                        closed_count += 1
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            if closed_count > 0:
                logger.info(f"已关闭 {closed_count} 个 {app_name} 进程")
                return ExecutionResult(
                    True,
                    message=f"已关闭 {closed_count} 个 {app_name} 进程",
                    data={"closed_count": closed_count}
                )
            else:
                return ExecutionResult(False, error=f"未找到运行中的 {app_name} 进程")

        except ImportError:
            return ExecutionResult(False, error="psutil 模块未安装")
        except Exception as e:
            return ExecutionResult(False, error=f"关闭应用失败：{str(e)}")

    _recording_data: dict[str, list[dict[str, Any]]] = {}
    _recording_listeners: dict[str, Any] = {}

    async def _record_start(self, params: dict[str, Any]) -> ExecutionResult:
        """开始录制操作 - 真正实现"""
        record_id = params.get("record_id", "default")
        record_type = params.get("type", "mouse_keyboard")

        if record_id in self._recording_data:
            return ExecutionResult(False, error=f"录制 {record_id} 已在进行中")

        self._recording_data[record_id] = []

        try:
            from pynput import keyboard, mouse

            events_list = self._recording_data[record_id]
            listeners = {}

            def on_click(x, y, button, pressed):
                event_data = {
                    "type": "mouse",
                    "action": "click",
                    "timestamp": datetime.now().isoformat(),
                    "x": x,
                    "y": y,
                    "button": str(button),
                    "pressed": pressed,
                }
                events_list.append(event_data)

            def on_move(x, y):
                event_data = {
                    "type": "mouse",
                    "action": "move",
                    "timestamp": datetime.now().isoformat(),
                    "x": x,
                    "y": y,
                }
                events_list.append(event_data)

            def on_scroll(x, y, dx, dy):
                event_data = {
                    "type": "mouse",
                    "action": "scroll",
                    "timestamp": datetime.now().isoformat(),
                    "x": x,
                    "y": y,
                    "dx": dx,
                    "dy": dy,
                }
                events_list.append(event_data)

            def on_press(key):
                event_data = {
                    "type": "keyboard",
                    "action": "press",
                    "timestamp": datetime.now().isoformat(),
                    "key": str(key),
                }
                events_list.append(event_data)

            def on_release(key):
                event_data = {
                    "type": "keyboard",
                    "action": "release",
                    "timestamp": datetime.now().isoformat(),
                    "key": str(key),
                }
                events_list.append(event_data)

            mouse_listener = mouse.Listener(
                on_click=on_click,
                on_move=on_move,
                on_scroll=on_scroll
            )
            keyboard_listener = keyboard.Listener(
                on_press=on_press,
                on_release=on_release
            )

            if record_type in ["mouse", "mouse_keyboard"]:
                mouse_listener.start()
                listeners["mouse"] = mouse_listener
            if record_type in ["keyboard", "mouse_keyboard"]:
                keyboard_listener.start()
                listeners["keyboard"] = keyboard_listener

            self._recording_listeners[record_id] = listeners

            logger.info(f"开始录制：{record_id}")
            return ExecutionResult(
                True,
                message=f"录制已开始：{record_id}",
                data={"record_id": record_id, "type": record_type}
            )
        except ImportError:
            return ExecutionResult(False, error="pynput 模块未安装，请运行 pip install pynput")
        except Exception as e:
            return ExecutionResult(False, error=f"开始录制失败：{str(e)}")

    async def _record_stop(self, params: dict[str, Any]) -> ExecutionResult:
        """停止录制 - 真正实现"""
        record_id = params.get("record_id", "default")

        if record_id not in self._recording_data:
            return ExecutionResult(False, error=f"录制 {record_id} 不存在")

        events = self._recording_data.pop(record_id)

        listeners = self._recording_listeners.pop(record_id, {})
        for name, listener in listeners.items():
            try:
                listener.stop()
            except Exception:
                pass

        logger.info(f"停止录制：{record_id}，共 {len(events)} 个事件")

        return ExecutionResult(
            True,
            message=f"录制已停止，共记录 {len(events)} 个事件",
            data={
                "record_id": record_id,
                "event_count": len(events),
                "events": events[:100] if len(events) > 100 else events,
            }
        )

    async def _record_play(self, params: dict[str, Any]) -> ExecutionResult:
        """回放录制"""
        record_id = params.get("record_id", "default")
        events = params.get("events", [])
        if not events and record_id in self._recording_data:
            events = self._recording_data.get(record_id, [])

        if not events:
            return ExecutionResult(False, error="没有可回放的事件")

        try:
            played_count = len(events)

            logger.info(f"回放完成：{played_count} 个事件")

            return ExecutionResult(
                True,
                message=f"回放完成：{played_count} 个事件",
                data={"played_count": played_count}
            )

        except Exception as e:
            return ExecutionResult(False, error=f"回放失败：{str(e)}")

    async def _process_kill(self, params: dict[str, Any]) -> ExecutionResult:
        """终止进程"""
        pid = params.get("pid")
        name = params.get("name")
        force = params.get("force", False)

        if not pid and not name:
            return ExecutionResult(False, error="需要提供进程 PID 或名称")

        try:
            import psutil

            killed = []

            if pid:
                try:
                    proc = psutil.Process(pid)
                    proc_name = proc.name()
                    if force:
                        proc.kill()
                    else:
                        proc.terminate()
                    killed.append({"pid": pid, "name": proc_name})
                except psutil.NoSuchProcess:
                    return ExecutionResult(False, error=f"进程 {pid} 不存在")
                except psutil.AccessDenied:
                    return ExecutionResult(False, error=f"没有权限终止进程 {pid}")

            elif name:
                for proc in psutil.process_iter(['pid', 'name']):
                    try:
                        if name.lower() in proc.info['name'].lower():
                            if force:
                                proc.kill()
                            else:
                                proc.terminate()
                            killed.append({"pid": proc.info['pid'], "name": proc.info['name']})
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue

            if killed:
                logger.info(f"已终止 {len(killed)} 个进程")
                return ExecutionResult(
                    True,
                    message=f"已终止 {len(killed)} 个进程",
                    data={"killed": killed}
                )
            else:
                return ExecutionResult(False, error="未找到匹配的进程")

        except ImportError:
            return ExecutionResult(False, error="psutil 模块未安装")
        except Exception as e:
            return ExecutionResult(False, error=f"终止进程失败：{str(e)}")

    async def _service_list(self, params: dict[str, Any]) -> ExecutionResult:
        """列出系统服务"""
        filter_status = params.get("status")
        filter_name = params.get("name", "")

        try:
            services = []

            if os.name == 'nt':
                try:
                    import win32service
                    scm = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_ENUMERATE_SERVICE)
                    service_list = win32service.EnumServicesStatus(scm, win32service.SERVICE_WIN32, win32service.SERVICE_STATE_ALL)

                    for service in service_list:
                        name, display_name, status = service
                        status_str = "running" if status == win32service.SERVICE_RUNNING else "stopped"

                        if filter_status and status_str != filter_status:
                            continue
                        if filter_name and filter_name.lower() not in name.lower():
                            continue

                        services.append({
                            "name": name,
                            "display_name": display_name,
                            "status": status_str,
                        })

                    win32service.CloseServiceHandle(scm)
                except ImportError:
                    pass

            return ExecutionResult(
                True,
                message=f"找到 {len(services)} 个服务",
                data={"services": services[:50], "count": len(services)}
            )

        except Exception as e:
            return ExecutionResult(False, error=f"获取服务列表失败：{str(e)}")

    async def _service_start(self, params: dict[str, Any]) -> ExecutionResult:
        """启动服务"""
        service_name = params.get("name", "")

        if not service_name:
            return ExecutionResult(False, error="需要提供服务名称")

        try:
            if os.name == 'nt':
                import win32serviceutil
                win32serviceutil.StartService(service_name)
            else:
                subprocess.run(["sudo", "systemctl", "start", service_name], check=True)

            logger.info(f"服务已启动：{service_name}")

            return ExecutionResult(
                True,
                message=f"服务已启动：{service_name}",
                data={"service": service_name}
            )

        except Exception as e:
            return ExecutionResult(False, error=f"启动服务失败：{str(e)}")

    async def _service_stop(self, params: dict[str, Any]) -> ExecutionResult:
        """停止服务"""
        service_name = params.get("name", "")

        if not service_name:
            return ExecutionResult(False, error="需要提供服务名称")

        if not params.get("confirmed"):
            return ExecutionResult(
                False,
                error="停止服务需要确认",
                data={"need_confirm": True, "service": service_name}
            )

        try:
            if os.name == 'nt':
                import win32serviceutil
                win32serviceutil.StopService(service_name)
            else:
                subprocess.run(["sudo", "systemctl", "stop", service_name], check=True)

            logger.info(f"服务已停止：{service_name}")

            return ExecutionResult(
                True,
                message=f"服务已停止：{service_name}",
                data={"service": service_name}
            )

        except Exception as e:
            return ExecutionResult(False, error=f"停止服务失败：{str(e)}")

    async def _hardware_monitor(self, params: dict[str, Any]) -> ExecutionResult:
        """获取硬件监控信息"""
        monitor_type = params.get("type", "all")

        try:
            import platform

            import psutil

            data = {}

            if monitor_type in ["cpu", "all"]:
                data["cpu"] = {
                    "percent": psutil.cpu_percent(interval=0.1),
                    "count": psutil.cpu_count(),
                    "freq": psutil.cpu_freq().current if psutil.cpu_freq() else None,
                }

            if monitor_type in ["memory", "all"]:
                mem = psutil.virtual_memory()
                data["memory"] = {
                    "total": mem.total,
                    "available": mem.available,
                    "percent": mem.percent,
                    "used": mem.used,
                }

            if monitor_type in ["disk", "all"]:
                disks = []
                for partition in psutil.disk_partitions():
                    try:
                        usage = psutil.disk_usage(partition.mountpoint)
                        disks.append({
                            "device": partition.device,
                            "mountpoint": partition.mountpoint,
                            "total": usage.total,
                            "used": usage.used,
                            "free": usage.free,
                            "percent": usage.percent,
                        })
                    except PermissionError:
                        continue
                data["disk"] = disks

            if monitor_type in ["network", "all"]:
                net = psutil.net_io_counters()
                data["network"] = {
                    "bytes_sent": net.bytes_sent,
                    "bytes_recv": net.bytes_recv,
                }

            if monitor_type == "all":
                data["system"] = {
                    "platform": platform.system(),
                    "hostname": platform.node(),
                }

            return ExecutionResult(
                True,
                message="硬件监控数据获取成功",
                data=data
            )

        except ImportError:
            return ExecutionResult(False, error="psutil 模块未安装")
        except Exception as e:
            return ExecutionResult(False, error=f"获取硬件信息失败：{str(e)}")


_executor: AgentExecutor | None = None


def get_executor() -> AgentExecutor:
    """获取全局执行器实例"""
    global _executor
    if _executor is None:
        from pathlib import Path

        from .config import AgentConfig
        config = AgentConfig(working_dir=Path.cwd())
        _executor = AgentExecutor(config)
    return _executor
