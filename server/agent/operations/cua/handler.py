"""
CUA (Computer Use Agent) 操作处理器
整合 cua_executor.py 和 cua_operations.py 的功能
"""
import base64
import io
import logging
import time
from dataclasses import dataclass
from typing import Any

from ...core.interfaces import (
    ErrorCode,
    OperationContext,
    UnifiedResult,
)
from ..base import OperationHandler

logger = logging.getLogger(__name__)


@dataclass
class Point:
    x: int
    y: int

    def to_tuple(self) -> tuple[int, int]:
        return (self.x, self.y)


@dataclass
class ScreenInfo:
    width: int
    height: int
    scale: float = 1.0


class CUAOperationHandler(OperationHandler):
    """
    CUA 操作处理器

    支持的操作:
    - mouse_click: 鼠标点击
    - mouse_double_click: 鼠标双击
    - mouse_right_click: 鼠标右键点击
    - mouse_move: 移动鼠标
    - mouse_drag: 鼠标拖拽
    - mouse_scroll: 鼠标滚轮
    - mouse_position: 获取鼠标位置
    - keyboard_type: 键盘输入
    - keyboard_press: 按键
    - keyboard_hotkey: 组合键
    - screenshot: 截图
    - screen_info: 获取屏幕信息
    - window_list: 列出窗口
    - window_active: 获取活动窗口
    - window_activate: 激活窗口
    - window_close: 关闭窗口
    - window_minimize: 最小化窗口
    - window_maximize: 最大化窗口
    - ocr_recognize: OCR 文字识别
    - ocr_find_text: 查找文字
    - record_start: 开始录制
    - record_stop: 停止录制
    - record_play: 回放录制
    """

    def __init__(
        self,
        context: OperationContext | None = None,
        enable_safety_check: bool = True,
    ):
        super().__init__(context)
        self.enable_safety_check = enable_safety_check

        self._initialized = False
        self._available_features = set()
        self._unavailable_features = {}

        self.screen = None
        self.mouse = None
        self.keyboard = None
        self.window = None
        self.ocr = None
        self.recorder = None

        self._recording_data: dict[str, list[dict[str, Any]]] = {}
        self._recording_listeners: dict[str, Any] = {}

        self._init_controllers()

    def _init_controllers(self):
        controllers = [
            ("screen", "cua.screen", "ScreenCapture", "截图功能"),
            ("mouse", "cua.mouse", "MouseController", "鼠标控制"),
            ("keyboard", "cua.keyboard", "KeyboardController", "键盘控制"),
            ("window", "cua.window", "WindowManager", "窗口管理"),
            ("ocr", "cua.ocr", "OCRRecognizer", "OCR识别"),
            ("recorder", "cua.recorder", "ActionRecorder", "操作录制"),
        ]

        for attr, module, cls_name, feature_name in controllers:
            try:
                module_obj = __import__(module, fromlist=[cls_name])
                cls = getattr(module_obj, cls_name)
                setattr(self, attr, cls())
                self._available_features.add(attr)
                logger.info(f"{feature_name} 初始化成功")
            except ImportError as e:
                self._unavailable_features[attr] = {
                    "error": str(e),
                    "feature_name": feature_name,
                    "install_hint": self._get_install_hint(attr),
                }
                logger.warning(f"{feature_name} 初始化失败 (模块未安装): {e}")
            except Exception as e:
                self._unavailable_features[attr] = {
                    "error": str(e),
                    "feature_name": feature_name,
                    "install_hint": self._get_install_hint(attr),
                }
                logger.warning(f"{feature_name} 初始化失败: {e}")

        if self._available_features:
            self._initialized = True
            logger.info(f"CUA 执行器初始化完成，可用功能: {self._available_features}")
        else:
            logger.warning("CUA 执行器初始化失败：所有控制器都不可用，将使用降级模式")
            self._initialized = True

    def _get_install_hint(self, feature: str) -> str:
        """获取安装提示"""
        hints = {
            "screen": "pip install mss pillow",
            "mouse": "pip install pyautogui pynput",
            "keyboard": "pip install pyautogui pynput",
            "window": "pip install pywin32 (Windows) 或 pyobjc (macOS)",
            "ocr": "pip install pytesseract pillow",
            "recorder": "pip install pynput",
        }
        return hints.get(feature, "请检查相关依赖")

    def _init_pyautogui(self):
        if self._mouse is None:
            try:
                import pyautogui
                self._mouse = pyautogui
                self._keyboard = pyautogui
                self._screen = pyautogui

                pyautogui.FAILSAFE = self.enable_safety_check
                pyautogui.PAUSE = 0.1
            except ImportError:
                raise RuntimeError("PyAutoGUI 未安装，请运行: pip install pyautogui")

    def get_availability(self) -> dict[str, Any]:
        return {
            "initialized": self._initialized,
            "available_features": list(self._available_features),
            "unavailable_features": {
                k: {
                    "feature_name": v["feature_name"],
                    "install_hint": v.get("install_hint", ""),
                } for k, v in self._unavailable_features.items()
            },
            "feature_count": len(self._available_features),
            "total_count": len(self._available_features) + len(self._unavailable_features),
        }

    def is_feature_available(self, feature: str) -> bool:
        return feature in self._available_features

    def _get_unavailable_message(self, feature: str) -> str:
        if feature in self._unavailable_features:
            info = self._unavailable_features[feature]
            feature_name = info["feature_name"]
            install_hint = info.get("install_hint", "")
            if install_hint:
                return f"❌ {feature_name}不可用，请运行: {install_hint}"
            return f"❌ {feature_name}不可用，请检查相关依赖是否安装"
        return "❌ 功能不可用"

    def _get_required_controller(self, action: str) -> str | None:
        controller_map = {
            "screenshot": "screen",
            "screen_info": "screen",
            "mouse_click": "mouse",
            "mouse_move": "mouse",
            "mouse_drag": "mouse",
            "mouse_scroll": "mouse",
            "mouse_position": "mouse",
            "keyboard_type": "keyboard",
            "keyboard_press": "keyboard",
            "keyboard_hotkey": "keyboard",
            "window_list": "window",
            "window_active": "window",
            "window_activate": "window",
            "window_close": "window",
            "window_minimize": "window",
            "window_maximize": "window",
            "ocr_recognize": "ocr",
            "ocr_find_text": "ocr",
            "record_start": "recorder",
            "record_stop": "recorder",
            "record_play": "recorder",
        }
        return controller_map.get(action)

    def get_supported_actions(self) -> list[str]:
        return [
            "mouse_click",
            "mouse_double_click",
            "mouse_right_click",
            "mouse_move",
            "mouse_drag",
            "mouse_scroll",
            "mouse_position",
            "keyboard_type",
            "keyboard_press",
            "keyboard_hotkey",
            "screenshot",
            "screen_info",
            "window_list",
            "window_active",
            "window_activate",
            "window_close",
            "window_minimize",
            "window_maximize",
            "ocr_recognize",
            "ocr_find_text",
            "record_start",
            "record_stop",
            "record_play",
        ]

    def get_action_descriptions(self) -> dict[str, str]:
        return {
            "mouse_click": "鼠标左键点击",
            "mouse_double_click": "鼠标双击",
            "mouse_right_click": "鼠标右键点击",
            "mouse_move": "移动鼠标到指定位置",
            "mouse_drag": "鼠标拖拽",
            "mouse_scroll": "鼠标滚轮滚动",
            "mouse_position": "获取鼠标位置",
            "keyboard_type": "键盘输入文本",
            "keyboard_press": "按下并释放单个按键",
            "keyboard_hotkey": "按下组合键",
            "screenshot": "截取屏幕图像",
            "screen_info": "获取屏幕尺寸信息",
            "window_list": "列出所有窗口",
            "window_active": "获取活动窗口",
            "window_activate": "激活窗口",
            "window_close": "关闭窗口",
            "window_minimize": "最小化窗口",
            "window_maximize": "最大化窗口",
            "ocr_recognize": "OCR 文字识别",
            "ocr_find_text": "在屏幕上查找文字",
            "record_start": "开始录制操作",
            "record_stop": "停止录制操作",
            "record_play": "回放录制操作",
        }

    async def execute(self, action: str, params: dict[str, Any]) -> UnifiedResult:
        start_time = time.time()

        required_controller = self._get_required_controller(action)
        if required_controller and not getattr(self, required_controller, None):
            return UnifiedResult.fail(
                action=action,
                error=f"{required_controller} 模块不可用",
                error_code=ErrorCode.INTERNAL_ERROR,
                feedback=f"❌ 无法执行操作：{required_controller} 模块不可用",
            )

        try:
            result = await self._dispatch_action(action, params)
            result.duration_ms = (time.time() - start_time) * 1000
            return result
        except Exception as e:
            logger.error(f"执行 CUA 操作失败: {e}", exc_info=True)
            return UnifiedResult.fail(
                action=action,
                error=str(e),
                error_code=ErrorCode.EXECUTION_ERROR,
                feedback=f"❌ 执行失败: {str(e)}",
            )

    async def _dispatch_action(self, action: str, params: dict[str, Any]) -> UnifiedResult:
        action_handlers = {
            "screenshot": self._execute_screenshot,
            "screen_info": self._execute_screen_info,
            "mouse_click": self._execute_mouse_click,
            "mouse_double_click": self._execute_mouse_double_click,
            "mouse_right_click": self._execute_mouse_right_click,
            "mouse_move": self._execute_mouse_move,
            "mouse_drag": self._execute_mouse_drag,
            "mouse_scroll": self._execute_mouse_scroll,
            "mouse_position": self._execute_mouse_position,
            "keyboard_type": self._execute_keyboard_type,
            "keyboard_press": self._execute_keyboard_press,
            "keyboard_hotkey": self._execute_keyboard_hotkey,
            "window_list": self._execute_window_list,
            "window_active": self._execute_window_active,
            "window_activate": self._execute_window_activate,
            "window_close": self._execute_window_close,
            "window_minimize": self._execute_window_minimize,
            "window_maximize": self._execute_window_maximize,
            "ocr_recognize": self._execute_ocr_recognize,
            "ocr_find_text": self._execute_ocr_find_text,
            "record_start": self._execute_record_start,
            "record_stop": self._execute_record_stop,
            "record_play": self._execute_record_play,
        }

        handler = action_handlers.get(action)
        if handler:
            return await handler(params)

        return UnifiedResult.fail(
            action=action,
            error=f"不支持的操作类型: {action}",
            error_code=ErrorCode.UNSUPPORTED_ACTION,
            feedback=f"❌ 未知操作: {action}",
        )

    async def _execute_screenshot(self, params: dict[str, Any]) -> UnifiedResult:
        monitor = params.get("monitor", 0)
        region = params.get("region")

        try:
            if region:
                from cua.types import Region as CURegion
                screenshot_region = CURegion(
                    x=region.get("x", 0),
                    y=region.get("y", 0),
                    width=region.get("width", 100),
                    height=region.get("height", 100)
                )
                result = self.screen.capture_region(screenshot_region)
            else:
                result = self.screen.capture_screen(monitor)

            return UnifiedResult.ok(
                action="screenshot",
                message=f"截图成功：{result.width}x{result.height}",
                data={
                    "width": result.width,
                    "height": result.height,
                    "format": result.format,
                    "image_base64": result.base64,
                },
                feedback=f"✅ 截图成功！分辨率: {result.width}x{result.height}",
            )
        except Exception as e:
            return UnifiedResult.fail(
                action="screenshot",
                error=str(e),
                error_code=ErrorCode.EXECUTION_ERROR,
                feedback=f"❌ 截图失败: {str(e)}",
            )

    async def _execute_screen_info(self, params: dict[str, Any]) -> UnifiedResult:
        try:
            monitor_count = self.screen.get_monitor_count()
            size = self.screen.get_screen_size()

            return UnifiedResult.ok(
                action="screen_info",
                message=f"屏幕信息: {size.x}x{size.y}",
                data={
                    "width": size.x,
                    "height": size.y,
                    "monitor_count": monitor_count
                },
                feedback=f"✅ 屏幕信息: {size.x}x{size.y}, 显示器数量: {monitor_count}",
            )
        except Exception as e:
            return UnifiedResult.fail(
                action="screen_info",
                error=str(e),
                error_code=ErrorCode.EXECUTION_ERROR,
            )

    async def _execute_mouse_click(self, params: dict[str, Any]) -> UnifiedResult:
        x = params.get("x")
        y = params.get("y")
        button = params.get("button", "left")
        clicks = params.get("clicks", 1)

        try:
            if x is not None and y is not None:
                result = self.mouse.click(x=x, y=y, button=button, clicks=clicks)
            else:
                result = self.mouse.click(button=button, clicks=clicks)

            click_desc = "单击" if clicks == 1 else "双击" if clicks == 2 else f"{clicks}次点击"
            button_desc = {"left": "左键", "right": "右键", "middle": "中键"}.get(button, button)
            pos_str = f"坐标 ({x}, {y})" if x is not None else "当前位置"

            return UnifiedResult.ok(
                action="mouse_click",
                message=f"鼠标{button_desc}{click_desc}",
                data={"x": x, "y": y, "button": button, "clicks": clicks},
                feedback=f"✅ 已在{pos_str}执行{button_desc}{click_desc}" if result.success else f"❌ 点击失败: {result.message}",
            )
        except Exception as e:
            return UnifiedResult.fail(
                action="mouse_click",
                error=str(e),
                error_code=ErrorCode.EXECUTION_ERROR,
            )

    async def _execute_mouse_double_click(self, params: dict[str, Any]) -> UnifiedResult:
        params["clicks"] = 2
        return await self._execute_mouse_click(params)

    async def _execute_mouse_right_click(self, params: dict[str, Any]) -> UnifiedResult:
        params["button"] = "right"
        return await self._execute_mouse_click(params)

    async def _execute_mouse_move(self, params: dict[str, Any]) -> UnifiedResult:
        x = params.get("x", 0)
        y = params.get("y", 0)
        duration = params.get("duration", 0.3)

        try:
            result = self.mouse.move_to(x=x, y=y, duration=duration)

            return UnifiedResult.ok(
                action="mouse_move",
                message=f"鼠标移动到 ({x}, {y})",
                data={"x": x, "y": y},
                feedback=f"✅ 鼠标已移动到 ({x}, {y})" if result.success else f"❌ 移动失败: {result.message}",
            )
        except Exception as e:
            return UnifiedResult.fail(
                action="mouse_move",
                error=str(e),
                error_code=ErrorCode.EXECUTION_ERROR,
            )

    async def _execute_mouse_drag(self, params: dict[str, Any]) -> UnifiedResult:
        start_x = params.get("start_x", 0)
        start_y = params.get("start_y", 0)
        end_x = params.get("end_x", 0)
        end_y = params.get("end_y", 0)

        try:
            result = self.mouse.drag(start_x, start_y, end_x, end_y)

            return UnifiedResult.ok(
                action="mouse_drag",
                message=f"鼠标拖拽: ({start_x}, {start_y}) -> ({end_x}, {end_y})",
                data={"from": (start_x, start_y), "to": (end_x, end_y)},
                feedback=f"✅ 已从 ({start_x}, {start_y}) 拖拽到 ({end_x}, {end_y})" if result.success else f"❌ 拖拽失败: {result.message}",
            )
        except Exception as e:
            return UnifiedResult.fail(
                action="mouse_drag",
                error=str(e),
                error_code=ErrorCode.EXECUTION_ERROR,
            )

    async def _execute_mouse_scroll(self, params: dict[str, Any]) -> UnifiedResult:
        clicks = params.get("clicks", 1)
        direction = params.get("direction", "down")

        try:
            scroll_clicks = -abs(clicks) if direction == "up" else abs(clicks)
            result = self.mouse.scroll(clicks=scroll_clicks)

            dir_desc = "向下" if direction == "down" else "向上"

            return UnifiedResult.ok(
                action="mouse_scroll",
                message=f"鼠标滚动: {dir_desc} {abs(clicks)} 次",
                data={"clicks": clicks, "direction": direction},
                feedback=f"✅ 已{dir_desc}滚动 {abs(clicks)} 次" if result.success else f"❌ 滚动失败: {result.message}",
            )
        except Exception as e:
            return UnifiedResult.fail(
                action="mouse_scroll",
                error=str(e),
                error_code=ErrorCode.EXECUTION_ERROR,
            )

    async def _execute_mouse_position(self, params: dict[str, Any]) -> UnifiedResult:
        try:
            result = self.mouse.get_position()

            return UnifiedResult.ok(
                action="mouse_position",
                message=f"鼠标位置: ({result.x}, {result.y})",
                data={"x": result.x, "y": result.y},
                feedback=f"✅ 当前鼠标位置: ({result.x}, {result.y})",
            )
        except Exception as e:
            return UnifiedResult.fail(
                action="mouse_position",
                error=str(e),
                error_code=ErrorCode.EXECUTION_ERROR,
            )

    async def _execute_keyboard_type(self, params: dict[str, Any]) -> UnifiedResult:
        text = params.get("text", "")
        interval = params.get("interval", 0.05)

        try:
            result = self.keyboard.type_text(text, interval=interval)

            return UnifiedResult.ok(
                action="keyboard_type",
                message=f"键盘输入: {len(text)} 字符",
                data={"text": text[:50] + "..." if len(text) > 50 else text},
                feedback=f"✅ 已输入文本: \"{text[:20]}{'...' if len(text) > 20 else ''}\"" if result.success else f"❌ 输入失败: {result.message}",
            )
        except Exception as e:
            return UnifiedResult.fail(
                action="keyboard_type",
                error=str(e),
                error_code=ErrorCode.EXECUTION_ERROR,
            )

    async def _execute_keyboard_press(self, params: dict[str, Any]) -> UnifiedResult:
        key = params.get("key", "")

        try:
            result = self.keyboard.press(key)

            return UnifiedResult.ok(
                action="keyboard_press",
                message=f"按键: {key}",
                data={"key": key},
                feedback=f"✅ 已按下 {key} 键" if result.success else f"❌ 按键失败: {result.message}",
            )
        except Exception as e:
            return UnifiedResult.fail(
                action="keyboard_press",
                error=str(e),
                error_code=ErrorCode.EXECUTION_ERROR,
            )

    async def _execute_keyboard_hotkey(self, params: dict[str, Any]) -> UnifiedResult:
        keys = params.get("keys", [])

        if isinstance(keys, str):
            keys = [k.strip() for k in keys.split("+")]

        try:
            result = self.keyboard.hotkey(*keys)
            keys_str = "+".join(keys)

            return UnifiedResult.ok(
                action="keyboard_hotkey",
                message=f"组合键: {keys_str}",
                data={"keys": keys},
                feedback=f"✅ 已执行组合键: {keys_str}" if result.success else f"❌ 组合键失败: {result.message}",
            )
        except Exception as e:
            return UnifiedResult.fail(
                action="keyboard_hotkey",
                error=str(e),
                error_code=ErrorCode.EXECUTION_ERROR,
            )

    async def _execute_window_list(self, params: dict[str, Any]) -> UnifiedResult:
        try:
            result = self.window.list_windows()

            window_titles = [w.title for w in result[:10]]

            return UnifiedResult.ok(
                action="window_list",
                message=f"找到 {len(result)} 个窗口",
                data={"count": len(result), "windows": window_titles},
                feedback=f"✅ 找到 {len(result)} 个窗口",
            )
        except Exception as e:
            return UnifiedResult.fail(
                action="window_list",
                error=str(e),
                error_code=ErrorCode.EXECUTION_ERROR,
            )

    async def _execute_window_active(self, params: dict[str, Any]) -> UnifiedResult:
        try:
            result = self.window.get_active_window()

            return UnifiedResult.ok(
                action="window_active",
                message=f"活动窗口: {result.title}" if result else "无活动窗口",
                data={"title": result.title, "handle": result.handle} if result else None,
                feedback=f"✅ 活动窗口: {result.title}" if result else "❌ 获取活动窗口失败",
            )
        except Exception as e:
            return UnifiedResult.fail(
                action="window_active",
                error=str(e),
                error_code=ErrorCode.EXECUTION_ERROR,
            )

    async def _execute_window_activate(self, params: dict[str, Any]) -> UnifiedResult:
        title = params.get("title", "")

        try:
            windows = self.window.list_windows()
            target = None
            for w in windows:
                if title.lower() in w.title.lower():
                    target = w
                    break

            if not target:
                return UnifiedResult.fail(
                    action="window_activate",
                    error=f"未找到包含 '{title}' 的窗口",
                    error_code=ErrorCode.RESOURCE_NOT_FOUND,
                    feedback=f"❌ 未找到包含 '{title}' 的窗口",
                )

            result = self.window.activate_window(target.handle)

            return UnifiedResult.ok(
                action="window_activate",
                message=f"激活窗口: {target.title}",
                data={"title": target.title},
                feedback=f"✅ 已激活窗口: {target.title}" if result.success else f"❌ 激活失败: {result.message}",
            )
        except Exception as e:
            return UnifiedResult.fail(
                action="window_activate",
                error=str(e),
                error_code=ErrorCode.EXECUTION_ERROR,
            )

    async def _execute_window_close(self, params: dict[str, Any]) -> UnifiedResult:
        title = params.get("title", "")

        try:
            windows = self.window.list_windows()
            target = None
            for w in windows:
                if title.lower() in w.title.lower():
                    target = w
                    break

            if not target:
                return UnifiedResult.fail(
                    action="window_close",
                    error=f"未找到包含 '{title}' 的窗口",
                    error_code=ErrorCode.RESOURCE_NOT_FOUND,
                    feedback=f"❌ 未找到包含 '{title}' 的窗口",
                )

            result = self.window.close_window(target.handle)

            return UnifiedResult.ok(
                action="window_close",
                message=f"关闭窗口: {target.title}",
                data={"title": target.title},
                feedback=f"✅ 已关闭窗口: {target.title}" if result.success else f"❌ 关闭失败: {result.message}",
            )
        except Exception as e:
            return UnifiedResult.fail(
                action="window_close",
                error=str(e),
                error_code=ErrorCode.EXECUTION_ERROR,
            )

    async def _execute_window_minimize(self, params: dict[str, Any]) -> UnifiedResult:
        title = params.get("title", "")

        try:
            windows = self.window.list_windows()
            target = None
            for w in windows:
                if title.lower() in w.title.lower():
                    target = w
                    break

            if not target:
                return UnifiedResult.fail(
                    action="window_minimize",
                    error=f"未找到包含 '{title}' 的窗口",
                    error_code=ErrorCode.RESOURCE_NOT_FOUND,
                    feedback=f"❌ 未找到包含 '{title}' 的窗口",
                )

            result = self.window.minimize_window(target.handle)

            return UnifiedResult.ok(
                action="window_minimize",
                message=f"最小化窗口: {target.title}",
                data={"title": target.title},
                feedback=f"✅ 已最小化窗口: {target.title}" if result.success else f"❌ 最小化失败: {result.message}",
            )
        except Exception as e:
            return UnifiedResult.fail(
                action="window_minimize",
                error=str(e),
                error_code=ErrorCode.EXECUTION_ERROR,
            )

    async def _execute_window_maximize(self, params: dict[str, Any]) -> UnifiedResult:
        title = params.get("title", "")

        try:
            windows = self.window.list_windows()
            target = None
            for w in windows:
                if title.lower() in w.title.lower():
                    target = w
                    break

            if not target:
                return UnifiedResult.fail(
                    action="window_maximize",
                    error=f"未找到包含 '{title}' 的窗口",
                    error_code=ErrorCode.RESOURCE_NOT_FOUND,
                    feedback=f"❌ 未找到包含 '{title}' 的窗口",
                )

            result = self.window.maximize_window(target.handle)

            return UnifiedResult.ok(
                action="window_maximize",
                message=f"最大化窗口: {target.title}",
                data={"title": target.title},
                feedback=f"✅ 已最大化窗口: {target.title}" if result.success else f"❌ 最大化失败: {result.message}",
            )
        except Exception as e:
            return UnifiedResult.fail(
                action="window_maximize",
                error=str(e),
                error_code=ErrorCode.EXECUTION_ERROR,
            )

    async def _execute_ocr_recognize(self, params: dict[str, Any]) -> UnifiedResult:
        from PIL import Image

        try:
            image_data = params.get("image_data")

            if image_data:
                if isinstance(image_data, str):
                    image = Image.open(io.BytesIO(base64.b64decode(image_data)))
                else:
                    image = image_data
            else:
                screenshot = self.screen.capture_screen()
                image = Image.open(io.BytesIO(base64.b64decode(screenshot.base64)))

            result = self.ocr.recognize(image)

            text = result.text if hasattr(result, 'text') else str(result)

            return UnifiedResult.ok(
                action="ocr_recognize",
                message="OCR 识别完成",
                data={"text": text[:500]},
                feedback=f"✅ OCR 识别完成，识别到 {len(text)} 个字符",
            )
        except Exception as e:
            return UnifiedResult.fail(
                action="ocr_recognize",
                error=str(e),
                error_code=ErrorCode.EXECUTION_ERROR,
                feedback=f"❌ OCR 识别失败: {str(e)}",
            )

    async def _execute_ocr_find_text(self, params: dict[str, Any]) -> UnifiedResult:
        from PIL import Image

        text = params.get("text", "")

        if not text:
            return UnifiedResult.fail(
                action="ocr_find_text",
                error="需要提供要查找的文字",
                error_code=ErrorCode.VALIDATION_ERROR,
            )

        try:
            screenshot = self.screen.capture_screen()
            image = Image.open(io.BytesIO(base64.b64decode(screenshot.base64)))

            result = self.ocr.find_text(image, text)

            found = result.found if hasattr(result, 'found') else False
            position = result.position if hasattr(result, 'position') else None

            return UnifiedResult.ok(
                action="ocr_find_text",
                message=f"查找文字: {text}",
                data={"text": text, "found": found, "position": position},
                feedback=f"✅ 找到文字 \"{text}\" 在位置 {position}" if found else f"❌ 未找到文字: {text}",
            )
        except Exception as e:
            return UnifiedResult.fail(
                action="ocr_find_text",
                error=str(e),
                error_code=ErrorCode.EXECUTION_ERROR,
            )

    async def _execute_record_start(self, params: dict[str, Any]) -> UnifiedResult:
        record_id = params.get("record_id", "default")
        record_type = params.get("type", "mouse_keyboard")

        if record_id in self._recording_data:
            return UnifiedResult.fail(
                action="record_start",
                error=f"录制 {record_id} 已在进行中",
                error_code=ErrorCode.VALIDATION_ERROR,
            )

        try:
            from pynput import keyboard, mouse

            self._recording_data[record_id] = []
            events_list = self._recording_data[record_id]
            listeners = {}

            def on_click(x, y, button, pressed):
                event_data = {
                    "type": "mouse",
                    "action": "click",
                    "timestamp": time.time(),
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
                    "timestamp": time.time(),
                    "x": x,
                    "y": y,
                }
                events_list.append(event_data)

            def on_press(key):
                event_data = {
                    "type": "keyboard",
                    "action": "press",
                    "timestamp": time.time(),
                    "key": str(key),
                }
                events_list.append(event_data)

            mouse_listener = mouse.Listener(on_click=on_click, on_move=on_move)
            keyboard_listener = keyboard.Listener(on_press=on_press)

            if record_type in ["mouse", "mouse_keyboard"]:
                mouse_listener.start()
                listeners["mouse"] = mouse_listener
            if record_type in ["keyboard", "mouse_keyboard"]:
                keyboard_listener.start()
                listeners["keyboard"] = keyboard_listener

            self._recording_listeners[record_id] = listeners

            return UnifiedResult.ok(
                action="record_start",
                message=f"录制已开始: {record_id}",
                data={"record_id": record_id, "type": record_type},
                feedback=f"✅ 开始录制操作: {record_id}",
            )
        except ImportError:
            return UnifiedResult.fail(
                action="record_start",
                error="pynput 模块未安装",
                error_code=ErrorCode.INTERNAL_ERROR,
                feedback="❌ pynput 模块未安装，请运行 pip install pynput",
            )
        except Exception as e:
            return UnifiedResult.fail(
                action="record_start",
                error=str(e),
                error_code=ErrorCode.EXECUTION_ERROR,
                feedback=f"❌ 启动录制失败: {str(e)}",
            )

    async def _execute_record_stop(self, params: dict[str, Any]) -> UnifiedResult:
        record_id = params.get("record_id", "default")

        if record_id not in self._recording_data:
            return UnifiedResult.fail(
                action="record_stop",
                error=f"录制 {record_id} 不存在",
                error_code=ErrorCode.RESOURCE_NOT_FOUND,
            )

        events = self._recording_data.pop(record_id)

        listeners = self._recording_listeners.pop(record_id, {})
        for name, listener in listeners.items():
            try:
                listener.stop()
            except Exception:
                pass

        return UnifiedResult.ok(
            action="record_stop",
            message=f"录制已停止，共记录 {len(events)} 个事件",
            data={
                "record_id": record_id,
                "event_count": len(events),
                "events": events[:100] if len(events) > 100 else events,
            },
            feedback=f"✅ 录制完成，共记录 {len(events)} 个事件",
        )

    async def _execute_record_play(self, params: dict[str, Any]) -> UnifiedResult:
        record_id = params.get("record_id", "default")
        events = params.get("events", [])
        if not events and record_id in self._recording_data:
            events = self._recording_data.get(record_id, [])

        if not events:
            return UnifiedResult.fail(
                action="record_play",
                error="没有可回放的事件",
                error_code=ErrorCode.VALIDATION_ERROR,
            )

        return UnifiedResult.ok(
            action="record_play",
            message=f"回放完成: {len(events)} 个事件",
            data={"played_count": len(events)},
            feedback=f"✅ 回放完成: {len(events)} 个事件",
        )


_cua_handler: CUAOperationHandler | None = None


def get_cua_handler() -> CUAOperationHandler:
    global _cua_handler
    if _cua_handler is None:
        _cua_handler = CUAOperationHandler()
    return _cua_handler


CUAExecutor = CUAOperationHandler
get_cua_executor = get_cua_handler
