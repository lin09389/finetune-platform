"""
CUA (Computer Use Agent) 基础技能
"""

from cua import (
    CUAError,
    KeyboardOperationError,
    MouseButton,
    MouseOperationError,
    OCRError,
    Region,
    ScreenshotError,
    WindowOperationError,
)
from cua.keyboard import KeyboardController
from cua.mouse import MouseController
from cua.ocr import OCRRecognizer
from cua.screen import ScreenCapture
from cua.window import WindowManager
from skills.base import SkillBase
from skills.models import (
    SkillCategory,
    SkillMetadata,
    SkillParameter,
    SkillParameterType,
    SkillResult,
)


class ScreenshotSkill(SkillBase):
    """屏幕截图技能"""

    @classmethod
    def get_metadata(cls) -> SkillMetadata:
        return SkillMetadata(
            name="screenshot",
            display_name="屏幕截图",
            description="捕获屏幕或指定区域的截图",
            version="1.0.0",
            category=SkillCategory.SYSTEM,
            tags=["screen", "capture", "screenshot", "cua"],
            parameters=[
                SkillParameter(
                    name="monitor",
                    type=SkillParameterType.INTEGER,
                    description="显示器索引（0 为主显示器）",
                    required=False,
                    default=0,
                    min_value=0,
                ),
                SkillParameter(
                    name="region",
                    type=SkillParameterType.OBJECT,
                    description="截图区域 {x, y, width, height}，不指定则截取整个屏幕",
                    required=False,
                    default=None,
                ),
            ],
            examples=[
                {},
                {"monitor": 0},
                {"region": {"x": 0, "y": 0, "width": 800, "height": 600}},
            ],
        )

    async def execute(self, **kwargs) -> SkillResult:
        monitor = kwargs.get("monitor", 0)
        region = kwargs.get("region")

        try:
            screen_capture = ScreenCapture()

            if region:
                region_obj = Region(
                    x=region.get("x", 0),
                    y=region.get("y", 0),
                    width=region.get("width", 800),
                    height=region.get("height", 600),
                )
                result = await screen_capture.capture_region_async(region_obj)
            else:
                result = await screen_capture.capture_screen_async(monitor)

            return SkillResult(
                success=True,
                data={
                    "base64": result.base64,
                    "width": result.width,
                    "height": result.height,
                    "format": result.format,
                    "monitor_index": result.monitor_index,
                    "region": {
                        "x": result.region.x,
                        "y": result.region.y,
                        "width": result.region.width,
                        "height": result.region.height,
                    } if result.region else None,
                },
                message="截图成功",
            )

        except ScreenshotError as e:
            return SkillResult(
                success=False,
                error=f"截图失败: {str(e)}",
                error_code="SCREENSHOT_ERROR",
            )
        except Exception as e:
            return SkillResult(
                success=False,
                error=f"截图时发生错误: {str(e)}",
                error_code="SCREENSHOT_UNKNOWN_ERROR",
            )


class MouseClickSkill(SkillBase):
    """鼠标点击技能"""

    @classmethod
    def get_metadata(cls) -> SkillMetadata:
        return SkillMetadata(
            name="mouse_click",
            display_name="鼠标点击",
            description="在指定位置执行鼠标点击操作",
            version="1.0.0",
            category=SkillCategory.SYSTEM,
            tags=["mouse", "click", "cua"],
            parameters=[
                SkillParameter(
                    name="x",
                    type=SkillParameterType.INTEGER,
                    description="点击位置的 X 坐标",
                    required=True,
                    min_value=0,
                ),
                SkillParameter(
                    name="y",
                    type=SkillParameterType.INTEGER,
                    description="点击位置的 Y 坐标",
                    required=True,
                    min_value=0,
                ),
                SkillParameter(
                    name="button",
                    type=SkillParameterType.STRING,
                    description="鼠标按钮（left/right/middle）",
                    required=False,
                    default="left",
                    enum=["left", "right", "middle"],
                ),
                SkillParameter(
                    name="clicks",
                    type=SkillParameterType.INTEGER,
                    description="点击次数",
                    required=False,
                    default=1,
                    min_value=1,
                    max_value=10,
                ),
            ],
            examples=[
                {"x": 100, "y": 200},
                {"x": 100, "y": 200, "button": "right"},
                {"x": 100, "y": 200, "clicks": 2},
            ],
            requires_confirmation=True,
        )

    async def execute(self, **kwargs) -> SkillResult:
        x = kwargs.get("x")
        y = kwargs.get("y")
        button = kwargs.get("button", "left")
        clicks = kwargs.get("clicks", 1)

        try:
            mouse = MouseController()
            button_enum = MouseButton(button)
            result = await mouse.click_async(x, y, button_enum, clicks)

            return SkillResult(
                success=True,
                data={
                    "x": x,
                    "y": y,
                    "button": button,
                    "clicks": clicks,
                },
                message=result.message,
            )

        except MouseOperationError as e:
            return SkillResult(
                success=False,
                error=f"鼠标点击失败: {str(e)}",
                error_code="MOUSE_CLICK_ERROR",
            )
        except CUAError as e:
            return SkillResult(
                success=False,
                error=f"CUA 错误: {str(e)}",
                error_code="CUA_ERROR",
            )
        except Exception as e:
            return SkillResult(
                success=False,
                error=f"鼠标点击时发生错误: {str(e)}",
                error_code="MOUSE_CLICK_UNKNOWN_ERROR",
            )


class MouseMoveSkill(SkillBase):
    """鼠标移动技能"""

    @classmethod
    def get_metadata(cls) -> SkillMetadata:
        return SkillMetadata(
            name="mouse_move",
            display_name="鼠标移动",
            description="将鼠标移动到指定位置",
            version="1.0.0",
            category=SkillCategory.SYSTEM,
            tags=["mouse", "move", "cua"],
            parameters=[
                SkillParameter(
                    name="x",
                    type=SkillParameterType.INTEGER,
                    description="目标位置的 X 坐标",
                    required=True,
                    min_value=0,
                ),
                SkillParameter(
                    name="y",
                    type=SkillParameterType.INTEGER,
                    description="目标位置的 Y 坐标",
                    required=True,
                    min_value=0,
                ),
                SkillParameter(
                    name="duration",
                    type=SkillParameterType.FLOAT,
                    description="移动持续时间（秒），0 表示瞬间移动",
                    required=False,
                    default=0.0,
                    min_value=0.0,
                    max_value=10.0,
                ),
            ],
            examples=[
                {"x": 100, "y": 200},
                {"x": 500, "y": 300, "duration": 0.5},
            ],
        )

    async def execute(self, **kwargs) -> SkillResult:
        x = kwargs.get("x")
        y = kwargs.get("y")
        duration = kwargs.get("duration", 0.0)

        try:
            mouse = MouseController()
            result = await mouse.move_to_async(x, y, duration if duration > 0 else None)

            return SkillResult(
                success=True,
                data={
                    "x": x,
                    "y": y,
                    "duration": duration,
                },
                message=result.message,
            )

        except MouseOperationError as e:
            return SkillResult(
                success=False,
                error=f"鼠标移动失败: {str(e)}",
                error_code="MOUSE_MOVE_ERROR",
            )
        except CUAError as e:
            return SkillResult(
                success=False,
                error=f"CUA 错误: {str(e)}",
                error_code="CUA_ERROR",
            )
        except Exception as e:
            return SkillResult(
                success=False,
                error=f"鼠标移动时发生错误: {str(e)}",
                error_code="MOUSE_MOVE_UNKNOWN_ERROR",
            )


class KeyboardTypeSkill(SkillBase):
    """键盘输入技能"""

    @classmethod
    def get_metadata(cls) -> SkillMetadata:
        return SkillMetadata(
            name="keyboard_type",
            display_name="键盘输入",
            description="模拟键盘输入文本",
            version="1.0.0",
            category=SkillCategory.SYSTEM,
            tags=["keyboard", "type", "input", "cua"],
            parameters=[
                SkillParameter(
                    name="text",
                    type=SkillParameterType.STRING,
                    description="要输入的文本内容",
                    required=True,
                ),
                SkillParameter(
                    name="interval",
                    type=SkillParameterType.FLOAT,
                    description="按键间隔时间（秒）",
                    required=False,
                    default=0.05,
                    min_value=0.0,
                    max_value=1.0,
                ),
            ],
            examples=[
                {"text": "Hello World"},
                {"text": "你好世界", "interval": 0.1},
            ],
            requires_confirmation=True,
        )

    async def execute(self, **kwargs) -> SkillResult:
        text = kwargs.get("text")
        interval = kwargs.get("interval", 0.05)

        try:
            keyboard = KeyboardController()
            result = await keyboard.type_text_async(text, interval)

            return SkillResult(
                success=True,
                data={
                    "text": text,
                    "text_length": len(text),
                    "interval": interval,
                },
                message=result.message,
            )

        except KeyboardOperationError as e:
            return SkillResult(
                success=False,
                error=f"键盘输入失败: {str(e)}",
                error_code="KEYBOARD_TYPE_ERROR",
            )
        except CUAError as e:
            return SkillResult(
                success=False,
                error=f"CUA 错误: {str(e)}",
                error_code="CUA_ERROR",
            )
        except Exception as e:
            return SkillResult(
                success=False,
                error=f"键盘输入时发生错误: {str(e)}",
                error_code="KEYBOARD_TYPE_UNKNOWN_ERROR",
            )


class WindowListSkill(SkillBase):
    """窗口列表技能"""

    @classmethod
    def get_metadata(cls) -> SkillMetadata:
        return SkillMetadata(
            name="window_list",
            display_name="窗口列表",
            description="获取当前所有窗口列表",
            version="1.0.0",
            category=SkillCategory.SYSTEM,
            tags=["window", "list", "cua"],
            parameters=[],
            examples=[{}],
        )

    async def execute(self, **kwargs) -> SkillResult:
        try:
            window_manager = WindowManager()
            windows = await window_manager.list_windows_async()

            window_list = [
                {
                    "title": win.title,
                    "handle": win.handle,
                    "x": win.x,
                    "y": win.y,
                    "width": win.width,
                    "height": win.height,
                    "is_visible": win.is_visible,
                    "is_focused": win.is_focused,
                }
                for win in windows
            ]

            return SkillResult(
                success=True,
                data={
                    "windows": window_list,
                    "count": len(window_list),
                },
                message=f"找到 {len(window_list)} 个窗口",
            )

        except WindowOperationError as e:
            return SkillResult(
                success=False,
                error=f"获取窗口列表失败: {str(e)}",
                error_code="WINDOW_LIST_ERROR",
            )
        except Exception as e:
            return SkillResult(
                success=False,
                error=f"获取窗口列表时发生错误: {str(e)}",
                error_code="WINDOW_LIST_UNKNOWN_ERROR",
            )


class AppLaunchSkill(SkillBase):
    """应用启动技能"""

    @classmethod
    def get_metadata(cls) -> SkillMetadata:
        return SkillMetadata(
            name="app_launch",
            display_name="启动应用",
            description="启动指定的应用程序",
            version="1.0.0",
            category=SkillCategory.SYSTEM,
            tags=["app", "launch", "application", "cua"],
            parameters=[
                SkillParameter(
                    name="app_name",
                    type=SkillParameterType.STRING,
                    description="应用程序名称或路径",
                    required=True,
                ),
            ],
            examples=[
                {"app_name": "notepad"},
                {"app_name": "calc"},
                {"app_name": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"},
            ],
            requires_confirmation=True,
        )

    async def execute(self, **kwargs) -> SkillResult:
        import asyncio
        import platform

        app_name = kwargs.get("app_name")

        try:
            system = platform.system().lower()

            if system == "windows":
                process = await asyncio.create_subprocess_exec(
                    "cmd",
                    "/c",
                    "start",
                    "",
                    app_name,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            elif system == "darwin":
                process = await asyncio.create_subprocess_exec(
                    "open",
                    "-a",
                    app_name,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            else:
                process = await asyncio.create_subprocess_exec(
                    app_name,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except asyncio.TimeoutError:
                pass

            return SkillResult(
                success=True,
                data={
                    "app_name": app_name,
                    "platform": system,
                },
                message=f"已启动应用: {app_name}",
            )

        except FileNotFoundError:
            return SkillResult(
                success=False,
                error=f"应用程序未找到: {app_name}",
                error_code="APP_NOT_FOUND",
            )
        except Exception as e:
            return SkillResult(
                success=False,
                error=f"启动应用失败: {str(e)}",
                error_code="APP_LAUNCH_ERROR",
            )


class FindTextSkill(SkillBase):
    """文本查找技能"""

    @classmethod
    def get_metadata(cls) -> SkillMetadata:
        return SkillMetadata(
            name="find_text",
            display_name="查找文本",
            description="在屏幕截图中查找指定文本的位置",
            version="1.0.0",
            category=SkillCategory.SYSTEM,
            tags=["ocr", "text", "find", "cua"],
            parameters=[
                SkillParameter(
                    name="text",
                    type=SkillParameterType.STRING,
                    description="要查找的文本",
                    required=True,
                ),
                SkillParameter(
                    name="lang",
                    type=SkillParameterType.STRING,
                    description="OCR 语言（如 chi_sim+eng）",
                    required=False,
                    default="chi_sim+eng",
                ),
                SkillParameter(
                    name="fuzzy",
                    type=SkillParameterType.BOOLEAN,
                    description="是否启用模糊匹配",
                    required=False,
                    default=False,
                ),
            ],
            examples=[
                {"text": "确定"},
                {"text": "Submit", "lang": "eng"},
                {"text": "保存", "fuzzy": True},
            ],
        )

    async def execute(self, **kwargs) -> SkillResult:
        text = kwargs.get("text")
        lang = kwargs.get("lang", "chi_sim+eng")
        fuzzy = kwargs.get("fuzzy", False)

        try:
            screen_capture = ScreenCapture()
            screenshot_result = await screen_capture.capture_screen_async()

            import io

            from PIL import Image

            image = Image.open(io.BytesIO(screenshot_result.image_data))

            ocr = OCRRecognizer()
            matches = ocr.find_all_text(image, text, lang, fuzzy=fuzzy)

            if not matches:
                return SkillResult(
                    success=True,
                    data={
                        "text": text,
                        "found": False,
                        "positions": [],
                    },
                    message=f"未找到文本: {text}",
                )

            positions = [
                {
                    "text": match["text"],
                    "x": match["coordinate"].x,
                    "y": match["coordinate"].y,
                    "region": {
                        "x": match["region"].x,
                        "y": match["region"].y,
                        "width": match["region"].width,
                        "height": match["region"].height,
                    },
                    "confidence": match["confidence"],
                }
                for match in matches
            ]

            return SkillResult(
                success=True,
                data={
                    "text": text,
                    "found": True,
                    "positions": positions,
                    "count": len(positions),
                },
                message=f"找到 {len(positions)} 处文本: {text}",
            )

        except OCRError as e:
            return SkillResult(
                success=False,
                error=f"OCR 识别失败: {str(e)}",
                error_code="OCR_ERROR",
            )
        except ScreenshotError as e:
            return SkillResult(
                success=False,
                error=f"截图失败: {str(e)}",
                error_code="SCREENSHOT_ERROR",
            )
        except Exception as e:
            return SkillResult(
                success=False,
                error=f"查找文本时发生错误: {str(e)}",
                error_code="FIND_TEXT_UNKNOWN_ERROR",
            )


CUA_SKILLS: list[type] = [
    ScreenshotSkill,
    MouseClickSkill,
    MouseMoveSkill,
    KeyboardTypeSkill,
    WindowListSkill,
    AppLaunchSkill,
    FindTextSkill,
]
