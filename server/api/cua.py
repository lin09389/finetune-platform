"""
CUA (Computer Use Agent) API 路由

Host control surface (mouse/keyboard/window/screenshot/OCR/record). All routes
require administrator role when ENABLE_AUTH is true (Phase-0 security).
"""
import base64
import io
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from PIL import Image
from pydantic import BaseModel, Field

from cua import (
    CUAError,
    MouseButton,
    OCRError,
    OperationType,
    PermissionDeniedError,
    PermissionLevel,
    Region,
    ScreenshotResult,
    TesseractNotInstalledError,
    WindowNotFoundError,
)
from cua.keyboard import KeyboardController
from cua.mouse import get_mouse_controller
from cua.ocr import OCRRecognizer
from cua.player import get_action_player
from cua.recorder import (
    ActionRecorder,
    RecordedAction,
    RecorderAlreadyRunningError,
    RecorderError,
    RecorderNotRunningError,
)
from cua.safety import get_safety_controller
from cua.screen import ScreenCapture
from cua.window import get_window_manager
from security.auth_middleware import require_cua_admin

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/cua",
    tags=["CUA - Computer Use Agent"],
    dependencies=[Depends(require_cua_admin)],
)

_screenshot_result: ScreenshotResult | None = None
_last_screenshot_base64: str | None = None


def get_screen_capture() -> ScreenCapture:
    return ScreenCapture()


def get_keyboard_controller() -> KeyboardController:
    return KeyboardController()


def get_ocr_recognizer() -> OCRRecognizer:
    return OCRRecognizer()


def get_action_recorder() -> ActionRecorder:
    global _action_recorder
    if '_action_recorder' not in globals():
        _action_recorder = ActionRecorder()
    return _action_recorder


def get_recordings_dir() -> Path:
    records_dir = Path("data/records")
    records_dir.mkdir(parents=True, exist_ok=True)
    return records_dir


class ScreenshotRequest(BaseModel):
    monitor: int = Field(default=0, ge=0, description="显示器索引")
    region: dict[str, int] | None = Field(default=None, description="截图区域 {x, y, width, height}")
    format: str = Field(default="png", description="图像格式")
    quality: int = Field(default=85, ge=1, le=100, description="JPEG 质量")


class MouseClickRequest(BaseModel):
    x: int = Field(..., ge=0, description="X 坐标")
    y: int = Field(..., ge=0, description="Y 坐标")
    button: str = Field(default="left", description="鼠标按钮: left, right, middle")
    clicks: int = Field(default=1, ge=1, description="点击次数")


class MouseMoveRequest(BaseModel):
    x: int = Field(..., description="X 坐标")
    y: int = Field(..., description="Y 坐标")
    duration: float = Field(default=0.0, ge=0, description="移动持续时间（秒）")


class MouseDragRequest(BaseModel):
    start_x: int = Field(..., description="起始 X 坐标")
    start_y: int = Field(..., description="起始 Y 坐标")
    end_x: int = Field(..., description="结束 X 坐标")
    end_y: int = Field(..., description="结束 Y 坐标")
    duration: float = Field(default=1.0, ge=0, description="拖拽持续时间（秒）")
    button: str = Field(default="left", description="鼠标按钮: left, right, middle")


class MouseScrollRequest(BaseModel):
    clicks: int = Field(..., description="滚动次数，正数向上，负数向下")
    x: int | None = Field(default=None, ge=0, description="X 坐标")
    y: int | None = Field(default=None, ge=0, description="Y 坐标")


class KeyboardTypeRequest(BaseModel):
    text: str = Field(..., description="输入文本")
    interval: float = Field(default=0.05, ge=0, description="按键间隔（秒）")


class KeyboardPressRequest(BaseModel):
    key: str = Field(..., description="按键名称")


class KeyboardHotkeyRequest(BaseModel):
    keys: list[str] = Field(..., description="组合键列表")


class WindowActionRequest(BaseModel):
    window_id: str = Field(..., description="窗口 ID 或标题")


class WindowMoveRequest(BaseModel):
    window_id: str = Field(..., description="窗口 ID 或标题")
    x: int = Field(..., description="X 坐标")
    y: int = Field(..., description="Y 坐标")


class WindowResizeRequest(BaseModel):
    window_id: str = Field(..., description="窗口 ID 或标题")
    width: int = Field(..., ge=1, description="窗口宽度")
    height: int = Field(..., ge=1, description="窗口高度")


class OCRRequest(BaseModel):
    image_base64: str | None = Field(default=None, description="Base64 编码的图像")
    region: dict[str, int] | None = Field(default=None, description="识别区域")
    lang: str = Field(default="chi_sim+eng", description="OCR 语言")


class FindTextRequest(BaseModel):
    text: str = Field(..., description="要查找的文本")
    lang: str = Field(default="chi_sim+eng", description="OCR 语言")
    fuzzy: bool = Field(default=False, description="是否模糊匹配")


class RecordActionRequest(BaseModel):
    action: str = Field(..., description="操作: start, stop, pause, resume")


class RecordSaveRequest(BaseModel):
    filename: str = Field(..., description="保存的录制文件名")


class RecordLoadRequest(BaseModel):
    filepath: str = Field(..., description="录制文件路径或文件名")


class PlaybackRequest(BaseModel):
    actions: list[dict[str, Any]] | None = Field(default=None, description="操作列表")
    filepath: str | None = Field(default=None, description="录制文件路径")
    speed: float = Field(default=1.0, ge=0.1, le=10.0, description="回放速度")


class PermissionRequest(BaseModel):
    level: str = Field(..., description="权限级别: read_only, interactive, full_control")


@router.post("/screenshot")
async def take_screenshot(request: ScreenshotRequest):
    global _screenshot_result, _last_screenshot_base64

    try:
        screen_capture = get_screen_capture()

        if request.region:
            region = Region(
                x=request.region["x"],
                y=request.region["y"],
                width=request.region["width"],
                height=request.region["height"]
            )
            result = await screen_capture.capture_region_async(region)
        else:
            result = await screen_capture.capture_screen_async(request.monitor)

        _screenshot_result = result
        _last_screenshot_base64 = result.base64

        return {
            "success": True,
            "width": result.width,
            "height": result.height,
            "format": result.format,
            "image": result.base64,
            "image_base64": result.base64,
            "monitor": result.monitor_index,
        }
    except CUAError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"截图失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"截图失败: {str(e)}")


@router.get("/screen/info")
async def get_screen_info():
    try:
        screen_capture = get_screen_capture()
        monitor_count = screen_capture.get_monitor_count()

        monitors = []
        for i in range(monitor_count):
            size = screen_capture.get_screen_size(i)
            monitors.append({
                "index": i,
                "width": size.x,
                "height": size.y,
            })

        primary_monitor = monitors[0] if monitors else {"width": 0, "height": 0}

        return {
            "width": primary_monitor["width"],
            "height": primary_monitor["height"],
            "monitorCount": monitor_count,
            "monitor_count": monitor_count,
            "monitors": monitors,
        }
    except Exception as e:
        logger.error(f"获取屏幕信息失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mouse/click")
async def mouse_click(request: MouseClickRequest):
    try:
        mouse = get_mouse_controller()

        button_map = {
            "left": MouseButton.LEFT,
            "right": MouseButton.RIGHT,
            "middle": MouseButton.MIDDLE,
        }
        button = button_map.get(request.button.lower(), MouseButton.LEFT)

        result = await mouse.click_async(request.x, request.y, button, request.clicks)

        return {
            "success": result.success,
            "message": result.message,
            "position": {"x": request.x, "y": request.y},
        }
    except CUAError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"鼠标点击失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mouse/move")
async def mouse_move(request: MouseMoveRequest):
    try:
        mouse = get_mouse_controller()
        result = await mouse.move_to_async(request.x, request.y, request.duration)

        return {
            "success": result.success,
            "message": result.message,
            "position": {"x": request.x, "y": request.y},
        }
    except CUAError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"鼠标移动失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mouse/drag")
async def mouse_drag(request: MouseDragRequest):
    try:
        mouse = get_mouse_controller()

        button_map = {
            "left": MouseButton.LEFT,
            "right": MouseButton.RIGHT,
            "middle": MouseButton.MIDDLE,
        }
        button = button_map.get(request.button.lower(), MouseButton.LEFT)

        result = await mouse.drag_async(
            request.start_x, request.start_y,
            request.end_x, request.end_y,
            request.duration, button
        )

        return {
            "success": result.success,
            "message": result.message,
            "start": {"x": request.start_x, "y": request.start_y},
            "end": {"x": request.end_x, "y": request.end_y},
        }
    except CUAError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"鼠标拖拽失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mouse/scroll")
async def mouse_scroll(request: MouseScrollRequest):
    try:
        mouse = get_mouse_controller()
        result = await mouse.scroll_async(request.clicks, request.x, request.y)

        return {
            "success": result.success,
            "message": result.message,
            "clicks": request.clicks,
        }
    except CUAError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"鼠标滚动失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/mouse/position")
async def get_mouse_position():
    try:
        mouse = get_mouse_controller()
        position = mouse.get_position()

        return {
            "x": position.x,
            "y": position.y,
        }
    except Exception as e:
        logger.error(f"获取鼠标位置失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/keyboard/type")
async def keyboard_type(request: KeyboardTypeRequest):
    try:
        keyboard = get_keyboard_controller()
        result = await keyboard.type_text_async(request.text, request.interval)

        return {
            "success": result.success,
            "message": result.message,
            "text_length": len(request.text),
        }
    except CUAError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"键盘输入失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/keyboard/press")
async def keyboard_press(request: KeyboardPressRequest):
    try:
        keyboard = get_keyboard_controller()
        result = await keyboard.press_async(request.key)

        return {
            "success": result.success,
            "message": result.message,
            "key": request.key,
        }
    except CUAError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"按键失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/keyboard/hotkey")
async def keyboard_hotkey(request: KeyboardHotkeyRequest):
    try:
        keyboard = get_keyboard_controller()
        result = await keyboard.hotkey_async(*request.keys)

        return {
            "success": result.success,
            "message": result.message,
            "keys": request.keys,
        }
    except CUAError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"组合键失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/window/list")
async def list_windows():
    try:
        window_manager = get_window_manager()
        windows = await window_manager.list_windows_async()

        return {
            "count": len(windows),
            "windows": [
                {
                    "title": w.title,
                    "handle": w.handle,
                    "x": w.x,
                    "y": w.y,
                    "width": w.width,
                    "height": w.height,
                    "is_visible": w.is_visible,
                    "is_focused": w.is_focused,
                }
                for w in windows
            ],
        }
    except Exception as e:
        logger.error(f"列出窗口失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/window/active")
async def get_active_window():
    try:
        window_manager = get_window_manager()
        window = await window_manager.get_active_window_async()

        return {
            "title": window.title,
            "handle": window.handle,
            "x": window.x,
            "y": window.y,
            "width": window.width,
            "height": window.height,
            "is_visible": window.is_visible,
            "is_focused": window.is_focused,
        }
    except CUAError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"获取活动窗口失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/window/activate")
async def activate_window(request: WindowActionRequest):
    try:
        window_manager = get_window_manager()
        result = await window_manager.activate_window_async(request.window_id)

        return {
            "success": result.success,
            "message": result.message,
        }
    except WindowNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except CUAError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"激活窗口失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/window/minimize")
async def minimize_window(request: WindowActionRequest):
    try:
        window_manager = get_window_manager()
        result = await window_manager.minimize_window_async(request.window_id)

        return {
            "success": result.success,
            "message": result.message,
        }
    except WindowNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except CUAError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"最小化窗口失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/window/maximize")
async def maximize_window(request: WindowActionRequest):
    try:
        window_manager = get_window_manager()
        result = await window_manager.maximize_window_async(request.window_id)

        return {
            "success": result.success,
            "message": result.message,
        }
    except WindowNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except CUAError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"最大化窗口失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/window/close")
async def close_window(request: WindowActionRequest):
    try:
        safety = get_safety_controller()
        window_manager = get_window_manager()

        await safety.validate_operation(OperationType.WINDOW_CLOSE, {"window_id": request.window_id})
        result = await window_manager.close_window_async(request.window_id)

        return {
            "success": result.success,
            "message": result.message,
        }
    except PermissionDeniedError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except WindowNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except CUAError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"关闭窗口失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/window/move")
async def move_window(request: WindowMoveRequest):
    try:
        window_manager = get_window_manager()
        result = await window_manager.move_window_async(request.window_id, request.x, request.y)

        return {
            "success": result.success,
            "message": result.message,
            "position": {"x": request.x, "y": request.y},
        }
    except WindowNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except CUAError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"移动窗口失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/window/resize")
async def resize_window(request: WindowResizeRequest):
    try:
        window_manager = get_window_manager()
        result = await window_manager.resize_window_async(request.window_id, request.width, request.height)

        return {
            "success": result.success,
            "message": result.message,
            "size": {"width": request.width, "height": request.height},
        }
    except WindowNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except CUAError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"调整窗口大小失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ocr")
async def ocr_recognize(request: OCRRequest):
    try:
        ocr = get_ocr_recognizer()

        if request.image_base64:
            image_data = base64.b64decode(request.image_base64)
            image = Image.open(io.BytesIO(image_data))
        elif _last_screenshot_base64:
            image_data = base64.b64decode(_last_screenshot_base64)
            image = Image.open(io.BytesIO(image_data))
        else:
            raise HTTPException(status_code=400, detail="未提供图像且无最近截图")

        if request.region:
            region = Region(
                x=request.region["x"],
                y=request.region["y"],
                width=request.region["width"],
                height=request.region["height"]
            )
            text = await ocr.recognize_region_async(image, region, request.lang)
        else:
            text = await ocr.recognize_async(image, request.lang)

        return {
            "success": True,
            "text": text,
            "lang": request.lang,
        }
    except TesseractNotInstalledError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except OCRError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"OCR 识别失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ocr/find-text")
async def find_text(request: FindTextRequest):
    try:
        ocr = get_ocr_recognizer()

        if not _last_screenshot_base64:
            raise HTTPException(status_code=400, detail="无最近截图，请先截图")

        image_data = base64.b64decode(_last_screenshot_base64)
        image = Image.open(io.BytesIO(image_data))

        matches = ocr.find_all_text(image, request.text, request.lang, request.fuzzy)

        return {
            "success": True,
            "text": request.text,
            "matches": [
                {
                    "text": m["text"],
                    "coordinate": {"x": m["coordinate"].x, "y": m["coordinate"].y},
                    "region": {
                        "x": m["region"].x,
                        "y": m["region"].y,
                        "width": m["region"].width,
                        "height": m["region"].height,
                    },
                    "confidence": m["confidence"],
                }
                for m in matches
            ],
            "count": len(matches),
        }
    except TesseractNotInstalledError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except OCRError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"查找文本失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/record/action")
async def record_action(request: RecordActionRequest):
    try:
        recorder = get_action_recorder()

        if request.action == "start":
            recorder.start_recording()
            return {"success": True, "message": "开始录制", "is_recording": True}
        elif request.action == "stop":
            actions = recorder.stop_recording()
            return {
                "success": True,
                "message": "停止录制",
                "is_recording": False,
                "action_count": len(actions),
            }
        elif request.action == "pause":
            recorder.pause_recording()
            return {"success": True, "message": "暂停录制", "is_paused": True}
        elif request.action == "resume":
            recorder.resume_recording()
            return {"success": True, "message": "恢复录制", "is_paused": False}
        else:
            raise HTTPException(status_code=400, detail=f"未知操作: {request.action}")
    except RecorderAlreadyRunningError:
        raise HTTPException(status_code=400, detail="录制器已在运行中")
    except RecorderNotRunningError:
        raise HTTPException(status_code=400, detail="录制器未运行")
    except RecorderError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"录制操作失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/record/actions")
async def get_recorded_actions():
    try:
        recorder = get_action_recorder()
        actions = recorder.get_actions()
        stats = recorder.get_statistics()

        return {
            "is_recording": recorder.is_recording(),
            "is_paused": recorder.is_paused(),
            "actions": [a.to_dict() for a in actions],
            "statistics": stats,
        }
    except Exception as e:
        logger.error(f"获取录制操作失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/record/actions")
async def clear_recorded_actions():
    try:
        recorder = get_action_recorder()
        recorder.clear_actions()
        return {"success": True, "message": "Recorded actions cleared"}
    except Exception as e:
        logger.error(f"清空录制动作失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/record/save")
async def save_recorded_actions(request: RecordSaveRequest):
    try:
        recorder = get_action_recorder()
        filename = request.filename.strip()
        if not filename:
            raise HTTPException(status_code=400, detail="Filename is required")

        if not filename.endswith(".json"):
            filename = f"{filename}.json"

        filepath = get_recordings_dir() / Path(filename).name
        recorder.save_to_file(str(filepath))
        return {
            "success": True,
            "message": "Recording saved",
            "filename": filepath.name,
            "filepath": str(filepath),
            "action_count": recorder.get_action_count(),
        }
    except RecorderError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"保存录制动作失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/record/load")
async def load_recorded_actions(request: RecordLoadRequest):
    try:
        filepath = Path(request.filepath)
        if not filepath.is_absolute():
            filepath = get_recordings_dir() / filepath.name

        recorder = get_action_recorder()
        actions = recorder.load_from_file(str(filepath))
        return {
            "success": True,
            "message": "Recording loaded",
            "filepath": str(filepath),
            "action_count": len(actions),
        }
    except RecorderError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"加载录制动作失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/record/files")
async def get_record_files():
    """获取已保存的录制文件列表"""
    try:
        files = []
        for f in get_recordings_dir().glob("*.json"):
            stat = f.stat()
            files.append({
                "filename": f.name,
                "filepath": str(f),
                "size": stat.st_size,
                "modified": stat.st_mtime,
            })

        return {"files": files}
    except Exception as e:
        logger.error(f"获取录制文件列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/record/play")
async def playback_actions(request: PlaybackRequest):
    try:
        player = get_action_player()

        if player.is_playing():
            raise HTTPException(status_code=400, detail="回放正在进行中")

        player.set_speed(request.speed)

        if request.filepath:
            result = await player.play_from_file_async(request.filepath)
        elif request.actions:
            actions = [
                RecordedAction(
                    action_type=a.get("action_type", a.get("action", "")),
                    timestamp=a.get("timestamp", a.get("delay", 0)),
                    data=a.get("data", a.get("params", {}))
                )
                for a in request.actions
            ]
            result = await player.play_async(actions)
        else:
            raise HTTPException(status_code=400, detail="未提供操作列表或文件路径")

        return {
            "success": result.success,
            "message": result.message,
            "data": result.data,
        }
    except RecorderError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"回放操作失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/safety/status")
async def get_safety_status():
    try:
        safety = get_safety_controller()
        permission_level = safety.get_permission_level().value
        failsafe_enabled = safety.is_failsafe_enabled()
        emergency_stop_triggered = safety.is_emergency_stop_triggered()

        return {
            "enabled": True,
            "permissionLevel": permission_level,
            "failsafeEnabled": failsafe_enabled,
            "auditEnabled": True,
            "permission_level": permission_level,
            "failsafe_enabled": failsafe_enabled,
            "emergency_stop_triggered": emergency_stop_triggered,
        }
    except Exception as e:
        logger.error(f"获取安全状态失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/safety/permission")
async def set_permission_level(request: PermissionRequest):
    try:
        safety = get_safety_controller()

        level_map = {
            "read_only": PermissionLevel.READ_ONLY,
            "interactive": PermissionLevel.INTERACTIVE,
            "full_control": PermissionLevel.FULL_CONTROL,
        }

        if request.level not in level_map:
            raise HTTPException(
                status_code=400,
                detail=f"无效的权限级别: {request.level}，可选值: {list(level_map.keys())}"
            )

        safety.set_permission_level(level_map[request.level])

        return {
            "success": True,
            "message": f"权限级别已设置为: {request.level}",
            "permission_level": request.level,
        }
    except Exception as e:
        logger.error(f"设置权限级别失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/safety/logs")
async def get_audit_logs(limit: int = Query(100, ge=1, le=1000, description="返回日志数量")):
    try:
        safety = get_safety_controller()
        logs = await safety.get_audit_logs(limit)

        return {
            "count": len(logs),
            "logs": [
                {
                    "operation_type": log.operation_type.value,
                    "permission_level": log.permission_level.value,
                    "parameters": log.parameters,
                    "result": log.result,
                    "timestamp": log.timestamp.isoformat(),
                    "duration_ms": log.duration_ms,
                    "error_message": log.error_message,
                }
                for log in logs
            ],
        }
    except Exception as e:
        logger.error(f"获取审计日志失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
