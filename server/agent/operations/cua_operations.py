"""
CUA (Computer Use Agent) 操作处理器
负责鼠标、键盘、屏幕等 GUI 自动化操作
"""
import base64
import io
import logging
from dataclasses import dataclass
from typing import Any

from .base import (
    OperationContext,
    OperationHandler,
    OperationResult,
)

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
    - keyboard_type: 键盘输入
    - keyboard_press: 按键
    - keyboard_hotkey: 组合键
    - screenshot: 截图
    - screen_info: 获取屏幕信息
    - ocr: OCR 文字识别
    - find_image: 查找图片
    """

    def __init__(
        self,
        context: OperationContext | None = None,
        enable_safety_check: bool = True,
    ):
        super().__init__(context)
        self.enable_safety_check = enable_safety_check
        self._mouse = None
        self._keyboard = None
        self._screen = None
        self._ocr_engine = None

    def _init_pyautogui(self):
        """延迟初始化 PyAutoGUI"""
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

    def get_supported_actions(self) -> list[str]:
        return [
            "mouse_click",
            "mouse_double_click",
            "mouse_right_click",
            "mouse_move",
            "mouse_drag",
            "mouse_scroll",
            "keyboard_type",
            "keyboard_press",
            "keyboard_hotkey",
            "screenshot",
            "screen_info",
            "ocr",
            "find_image",
        ]

    def get_action_descriptions(self) -> dict[str, str]:
        return {
            "mouse_click": "鼠标左键点击",
            "mouse_double_click": "鼠标双击",
            "mouse_right_click": "鼠标右键点击",
            "mouse_move": "移动鼠标到指定位置",
            "mouse_drag": "鼠标拖拽",
            "mouse_scroll": "鼠标滚轮滚动",
            "keyboard_type": "键盘输入文本",
            "keyboard_press": "按下并释放单个按键",
            "keyboard_hotkey": "按下组合键",
            "screenshot": "截取屏幕图像",
            "screen_info": "获取屏幕尺寸信息",
            "ocr": "OCR 文字识别",
            "find_image": "在屏幕上查找图片",
        }

    def validate_params(self, action: str, params: dict[str, Any]) -> str | None:
        validators = {
            "mouse_click": self._validate_mouse_position,
            "mouse_double_click": self._validate_mouse_position,
            "mouse_right_click": self._validate_mouse_position,
            "mouse_move": self._validate_mouse_position,
            "mouse_drag": self._validate_mouse_drag,
            "mouse_scroll": self._validate_mouse_scroll,
            "keyboard_type": self._validate_keyboard_type,
            "keyboard_press": self._validate_keyboard_press,
            "keyboard_hotkey": self._validate_keyboard_hotkey,
            "screenshot": lambda _p: None,
            "screen_info": lambda _p: None,
            "ocr": self._validate_ocr,
            "find_image": self._validate_find_image,
        }

        validator = validators.get(action)
        if validator:
            return validator(params)

        return None

    def _validate_mouse_position(self, params: dict[str, Any]) -> str | None:
        if "x" not in params or "y" not in params:
            return "缺少必需参数: x, y"
        return None

    def _validate_mouse_drag(self, params: dict[str, Any]) -> str | None:
        if "start_x" not in params or "start_y" not in params:
            return "缺少必需参数: start_x, start_y"
        if "end_x" not in params or "end_y" not in params:
            return "缺少必需参数: end_x, end_y"
        return None

    def _validate_mouse_scroll(self, params: dict[str, Any]) -> str | None:
        if "clicks" not in params:
            return "缺少必需参数: clicks"
        return None

    def _validate_keyboard_type(self, params: dict[str, Any]) -> str | None:
        if "text" not in params:
            return "缺少必需参数: text"
        return None

    def _validate_keyboard_press(self, params: dict[str, Any]) -> str | None:
        if "key" not in params:
            return "缺少必需参数: key"
        return None

    def _validate_keyboard_hotkey(self, params: dict[str, Any]) -> str | None:
        if "keys" not in params:
            return "缺少必需参数: keys"
        return None

    def _validate_ocr(self, params: dict[str, Any]) -> str | None:
        if "image" not in params and "region" not in params:
            return "缺少必需参数: image 或 region"
        return None

    def _validate_find_image(self, params: dict[str, Any]) -> str | None:
        if "template" not in params:
            return "缺少必需参数: template"
        return None

    async def execute(self, action: str, params: dict[str, Any]) -> OperationResult:
        self._init_pyautogui()

        handlers = {
            "mouse_click": self._mouse_click,
            "mouse_double_click": self._mouse_double_click,
            "mouse_right_click": self._mouse_right_click,
            "mouse_move": self._mouse_move,
            "mouse_drag": self._mouse_drag,
            "mouse_scroll": self._mouse_scroll,
            "keyboard_type": self._keyboard_type,
            "keyboard_press": self._keyboard_press,
            "keyboard_hotkey": self._keyboard_hotkey,
            "screenshot": self._screenshot,
            "screen_info": self._screen_info,
            "ocr": self._ocr,
            "find_image": self._find_image,
        }

        handler = handlers.get(action)
        if handler:
            return await handler(params)

        return OperationResult.fail(
            error=f"未实现的操作: {action}",
            error_code="NOT_IMPLEMENTED"
        )

    async def _mouse_click(self, params: dict[str, Any]) -> OperationResult:
        """鼠标点击"""
        x, y = params["x"], params["y"]
        button = params.get("button", "left")

        self._mouse.click(x, y, button=button)

        return OperationResult.ok(
            message=f"鼠标点击: ({x}, {y})",
            data={"x": x, "y": y, "button": button}
        )

    async def _mouse_double_click(self, params: dict[str, Any]) -> OperationResult:
        """鼠标双击"""
        x, y = params["x"], params["y"]

        self._mouse.doubleClick(x, y)

        return OperationResult.ok(
            message=f"鼠标双击: ({x}, {y})",
            data={"x": x, "y": y}
        )

    async def _mouse_right_click(self, params: dict[str, Any]) -> OperationResult:
        """鼠标右键点击"""
        x, y = params["x"], params["y"]

        self._mouse.rightClick(x, y)

        return OperationResult.ok(
            message=f"鼠标右键点击: ({x}, {y})",
            data={"x": x, "y": y}
        )

    async def _mouse_move(self, params: dict[str, Any]) -> OperationResult:
        """移动鼠标"""
        x, y = params["x"], params["y"]
        duration = params.get("duration", 0.2)

        self._mouse.moveTo(x, y, duration=duration)

        return OperationResult.ok(
            message=f"鼠标移动到: ({x}, {y})",
            data={"x": x, "y": y}
        )

    async def _mouse_drag(self, params: dict[str, Any]) -> OperationResult:
        """鼠标拖拽"""
        start_x, start_y = params["start_x"], params["start_y"]
        end_x, end_y = params["end_x"], params["end_y"]
        duration = params.get("duration", 0.5)

        self._mouse.moveTo(start_x, start_y)
        self._mouse.dragTo(end_x, end_y, duration=duration)

        return OperationResult.ok(
            message=f"鼠标拖拽: ({start_x}, {start_y}) -> ({end_x}, {end_y})",
            data={"start": (start_x, start_y), "end": (end_x, end_y)}
        )

    async def _mouse_scroll(self, params: dict[str, Any]) -> OperationResult:
        """鼠标滚轮"""
        clicks = params["clicks"]
        x = params.get("x")
        y = params.get("y")

        self._mouse.scroll(clicks, x, y)

        return OperationResult.ok(
            message=f"鼠标滚轮: {clicks}",
            data={"clicks": clicks}
        )

    async def _keyboard_type(self, params: dict[str, Any]) -> OperationResult:
        """键盘输入"""
        text = params["text"]
        interval = params.get("interval", 0.05)

        self._keyboard.typewrite(text, interval=interval)

        return OperationResult.ok(
            message=f"键盘输入: {len(text)} 字符",
            data={"length": len(text)}
        )

    async def _keyboard_press(self, params: dict[str, Any]) -> OperationResult:
        """按键"""
        key = params["key"]

        self._keyboard.press(key)

        return OperationResult.ok(
            message=f"按键: {key}",
            data={"key": key}
        )

    async def _keyboard_hotkey(self, params: dict[str, Any]) -> OperationResult:
        """组合键"""
        keys = params["keys"]

        self._keyboard.hotkey(*keys)

        return OperationResult.ok(
            message=f"组合键: {'+'.join(keys)}",
            data={"keys": keys}
        )

    async def _screenshot(self, params: dict[str, Any]) -> OperationResult:
        """截图"""
        region = params.get("region")

        if region:
            screenshot = self._screen.screenshot(region=region)
        else:
            screenshot = self._screen.screenshot()

        buffer = io.BytesIO()
        screenshot.save(buffer, format="PNG")
        image_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

        return OperationResult.ok(
            message="截图成功",
            data={
                "image": image_base64,
                "width": screenshot.width,
                "height": screenshot.height,
            }
        )

    async def _screen_info(self, params: dict[str, Any]) -> OperationResult:
        """获取屏幕信息"""
        size = self._screen.size()

        return OperationResult.ok(
            message="获取屏幕信息成功",
            data={
                "width": size.width,
                "height": size.height,
            }
        )

    async def _ocr(self, params: dict[str, Any]) -> OperationResult:
        """OCR 文字识别"""
        try:
            import pytesseract
            from PIL import Image

            if "image" in params:
                image_data = base64.b64decode(params["image"])
                image = Image.open(io.BytesIO(image_data))
            else:
                screenshot = self._screen.screenshot()
                image = screenshot

            if "region" in params:
                region = params["region"]
                image = image.crop(region)

            lang = params.get("lang", "chi_sim+eng")
            text = pytesseract.image_to_string(image, lang=lang)

            return OperationResult.ok(
                message="OCR 识别成功",
                data={"text": text.strip()}
            )

        except ImportError:
            return OperationResult.fail(
                error="Tesseract 未安装，请运行: pip install pytesseract",
                error_code="TESSERACT_NOT_INSTALLED"
            )

    async def _find_image(self, params: dict[str, Any]) -> OperationResult:
        """查找图片"""
        template = params["template"]
        confidence = params.get("confidence", 0.9)

        try:
            template_data = base64.b64decode(template)
            template_image = io.BytesIO(template_data)

            position = self._screen.locateOnScreen(
                template_image,
                confidence=confidence
            )

            if position:
                return OperationResult.ok(
                    message="找到图片",
                    data={
                        "found": True,
                        "x": position.left,
                        "y": position.top,
                        "width": position.width,
                        "height": position.height,
                    }
                )
            else:
                return OperationResult.ok(
                    message="未找到图片",
                    data={"found": False}
                )

        except Exception as e:
            return OperationResult.fail(
                error=f"查找图片失败: {e}",
                error_code="FIND_IMAGE_ERROR"
            )
