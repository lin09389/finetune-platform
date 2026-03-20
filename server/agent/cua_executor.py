"""
智能 CUA 执行器
自动判断并执行 CUA 操作，提供执行反馈
"""
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum

from agent.config import ActionType

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """执行结果"""
    success: bool
    action: str
    description: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    feedback: str = ""
    duration_ms: float = 0.0


class CUAExecutor:
    """
    CUA 智能执行器
    
    自动判断用户意图并执行相应的 CUA 操作
    提供详细的执行反馈
    支持降级方案
    """
    
    def __init__(self):
        self._init_controllers()
        self._init_fallback_handlers()
    
    def _init_controllers(self):
        """初始化控制器"""
        self._initialized = False
        self._available_features = set()
        self._unavailable_features = {}
        
        self.screen = None
        self.mouse = None
        self.keyboard = None
        self.window = None
        self.ocr = None
        self.recorder = None
        
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
            except Exception as e:
                self._unavailable_features[attr] = {
                    "error": str(e),
                    "feature_name": feature_name,
                }
                logger.warning(f"{feature_name} 初始化失败: {e}")
        
        if self._available_features:
            self._initialized = True
            logger.info(f"CUA 执行器初始化完成，可用功能: {self._available_features}")
        else:
            logger.warning("CUA 执行器初始化失败：所有控制器都不可用")
    
    def _init_fallback_handlers(self):
        """初始化降级处理器"""
        self._fallback_handlers = {
            ActionType.SCREENSHOT: self._fallback_screenshot,
            ActionType.MOUSE_CLICK: self._fallback_mouse_click,
            ActionType.MOUSE_MOVE: self._fallback_mouse_move,
            ActionType.KEYBOARD_TYPE: self._fallback_keyboard_type,
            ActionType.WINDOW_LIST: self._fallback_window_list,
            ActionType.OCR_RECOGNIZE: self._fallback_ocr,
        }
    
    def get_availability(self) -> Dict[str, Any]:
        """获取功能可用性状态"""
        return {
            "initialized": self._initialized,
            "available_features": list(self._available_features),
            "unavailable_features": {
                k: v["feature_name"] for k, v in self._unavailable_features.items()
            },
            "feature_count": len(self._available_features),
            "total_count": len(self._available_features) + len(self._unavailable_features),
        }
    
    def is_feature_available(self, feature: str) -> bool:
        """检查功能是否可用"""
        return feature in self._available_features
    
    def _get_unavailable_message(self, feature: str) -> str:
        """获取功能不可用消息"""
        if feature in self._unavailable_features:
            feature_name = self._unavailable_features[feature]["feature_name"]
            return f"❌ {feature_name}不可用，请检查相关依赖是否安装"
        return f"❌ 功能不可用"
    
    async def execute(self, action: ActionType, params: Dict[str, Any]) -> ExecutionResult:
        """
        执行 CUA 操作
        
        Args:
            action: 操作类型
            params: 操作参数
            
        Returns:
            ExecutionResult: 执行结果
        """
        import time
        start_time = time.time()
        
        # 检查特定控制器是否可用
        required_controller = self._get_required_controller(action)
        if required_controller and not getattr(self, required_controller, None):
            return ExecutionResult(
                success=False,
                action=action.value,
                description=f"{required_controller} 模块不可用",
                error=f"执行 {action.value} 需要 {required_controller} 模块，但该模块未初始化",
                feedback=f"❌ 无法执行操作：{required_controller} 模块不可用"
            )
        
        try:
            result = await self._dispatch_action(action, params)
            
            duration_ms = (time.time() - start_time) * 1000
            result.duration_ms = duration_ms
            
            return result
            
        except Exception as e:
            logger.error(f"执行 CUA 操作失败: {e}", exc_info=True)
            return ExecutionResult(
                success=False,
                action=action.value,
                description=f"执行 {action.value} 失败",
                error=str(e),
                feedback=f"❌ 执行失败: {str(e)}"
            )
    
    def _get_required_controller(self, action: ActionType) -> Optional[str]:
        """获取操作所需的控制器"""
        controller_map = {
            ActionType.SCREENSHOT: "screen",
            ActionType.SCREEN_INFO: "screen",
            ActionType.MOUSE_CLICK: "mouse",
            ActionType.MOUSE_MOVE: "mouse",
            ActionType.MOUSE_DRAG: "mouse",
            ActionType.MOUSE_SCROLL: "mouse",
            ActionType.MOUSE_POSITION: "mouse",
            ActionType.KEYBOARD_TYPE: "keyboard",
            ActionType.KEYBOARD_PRESS: "keyboard",
            ActionType.KEYBOARD_HOTKEY: "keyboard",
            ActionType.WINDOW_LIST: "window",
            ActionType.WINDOW_ACTIVE: "window",
            ActionType.WINDOW_ACTIVATE: "window",
            ActionType.WINDOW_CLOSE: "window",
            ActionType.WINDOW_MINIMIZE: "window",
            ActionType.WINDOW_MAXIMIZE: "window",
            ActionType.OCR_RECOGNIZE: "ocr",
            ActionType.OCR_FIND_TEXT: "ocr",
            ActionType.RECORD_START: "recorder",
            ActionType.RECORD_STOP: "recorder",
            ActionType.RECORD_PLAY: "recorder",
        }
        return controller_map.get(action)
    
    async def _dispatch_action(self, action: ActionType, params: Dict[str, Any]) -> ExecutionResult:
        """分发操作到对应处理器"""
        
        # 屏幕操作
        if action == ActionType.SCREENSHOT:
            return await self._execute_screenshot(params)
        elif action == ActionType.SCREEN_INFO:
            return await self._execute_screen_info(params)
        
        # 鼠标操作
        elif action == ActionType.MOUSE_CLICK:
            return await self._execute_mouse_click(params)
        elif action == ActionType.MOUSE_MOVE:
            return await self._execute_mouse_move(params)
        elif action == ActionType.MOUSE_DRAG:
            return await self._execute_mouse_drag(params)
        elif action == ActionType.MOUSE_SCROLL:
            return await self._execute_mouse_scroll(params)
        elif action == ActionType.MOUSE_POSITION:
            return await self._execute_mouse_position(params)
        
        # 键盘操作
        elif action == ActionType.KEYBOARD_TYPE:
            return await self._execute_keyboard_type(params)
        elif action == ActionType.KEYBOARD_PRESS:
            return await self._execute_keyboard_press(params)
        elif action == ActionType.KEYBOARD_HOTKEY:
            return await self._execute_keyboard_hotkey(params)
        
        # 窗口操作
        elif action == ActionType.WINDOW_LIST:
            return await self._execute_window_list(params)
        elif action == ActionType.WINDOW_ACTIVE:
            return await self._execute_window_active(params)
        elif action == ActionType.WINDOW_ACTIVATE:
            return await self._execute_window_activate(params)
        elif action == ActionType.WINDOW_CLOSE:
            return await self._execute_window_close(params)
        elif action == ActionType.WINDOW_MINIMIZE:
            return await self._execute_window_minimize(params)
        elif action == ActionType.WINDOW_MAXIMIZE:
            return await self._execute_window_maximize(params)
        
        # OCR 操作
        elif action == ActionType.OCR_RECOGNIZE:
            return await self._execute_ocr_recognize(params)
        elif action == ActionType.OCR_FIND_TEXT:
            return await self._execute_ocr_find_text(params)
        
        # 录制操作
        elif action == ActionType.RECORD_START:
            return await self._execute_record_start(params)
        elif action == ActionType.RECORD_STOP:
            return await self._execute_record_stop(params)
        elif action == ActionType.RECORD_PLAY:
            return await self._execute_record_play(params)
        
        else:
            return ExecutionResult(
                success=False,
                action=action.value,
                description="未知操作类型",
                error=f"不支持的操作类型: {action.value}",
                feedback=f"❌ 未知操作: {action.value}"
            )
    
    # ==================== 屏幕操作 ====================
    
    async def _execute_screenshot(self, params: Dict[str, Any]) -> ExecutionResult:
        """执行截图"""
        monitor = params.get("monitor", 0)
        
        result = self.screen.capture_screen(monitor=monitor)
        
        return ExecutionResult(
            success=True,
            action="screenshot",
            description="截取屏幕截图",
            data={
                "width": result.width,
                "height": result.height,
                "format": result.format,
                "image_base64": result.base64,
            },
            feedback=f"✅ 截图成功！分辨率: {result.width}x{result.height}"
        )
    
    async def _execute_screen_info(self, params: Dict[str, Any]) -> ExecutionResult:
        """获取屏幕信息"""
        monitor_count = self.screen.get_monitor_count()
        size = self.screen.get_screen_size()
        
        return ExecutionResult(
            success=True,
            action="screen_info",
            description="获取屏幕信息",
            data={
                "width": size.x,
                "height": size.y,
                "monitor_count": monitor_count
            },
            feedback=f"✅ 屏幕信息: {size.x}x{size.y}, 显示器数量: {monitor_count}"
        )
    
    # ==================== 鼠标操作 ====================
    
    async def _execute_mouse_click(self, params: Dict[str, Any]) -> ExecutionResult:
        """执行鼠标点击"""
        x = params.get("x")
        y = params.get("y")
        button = params.get("button", "left")
        clicks = params.get("clicks", 1)
        
        if x is not None and y is not None:
            result = self.mouse.click(x=x, y=y, button=button, clicks=clicks)
        else:
            result = self.mouse.click(button=button, clicks=clicks)
        
        click_desc = "单击" if clicks == 1 else "双击" if clicks == 2 else f"{clicks}次点击"
        button_desc = {"left": "左键", "right": "右键", "middle": "中键"}.get(button, button)
        
        pos_str = f"坐标 ({x}, {y})" if x is not None else "当前位置"
        
        return ExecutionResult(
            success=result.success,
            action="mouse_click",
            description=f"鼠标{button_desc}{click_desc}",
            data={"x": x, "y": y, "button": button, "clicks": clicks},
            feedback=f"✅ 已在{pos_str}执行{button_desc}{click_desc}" if result.success else f"❌ 点击失败: {result.message}"
        )
    
    async def _execute_mouse_move(self, params: Dict[str, Any]) -> ExecutionResult:
        """执行鼠标移动"""
        x = params.get("x", 0)
        y = params.get("y", 0)
        duration = params.get("duration", 0.3)
        
        result = self.mouse.move_to(x=x, y=y, duration=duration)
        
        return ExecutionResult(
            success=result.success,
            action="mouse_move",
            description="移动鼠标",
            data={"x": x, "y": y},
            feedback=f"✅ 鼠标已移动到 ({x}, {y})" if result.success else f"❌ 移动失败: {result.message}"
        )
    
    async def _execute_mouse_drag(self, params: Dict[str, Any]) -> ExecutionResult:
        """执行鼠标拖拽"""
        start_x = params.get("start_x", 0)
        start_y = params.get("start_y", 0)
        end_x = params.get("end_x", 0)
        end_y = params.get("end_y", 0)
        
        result = self.mouse.drag(start_x, start_y, end_x, end_y)
        
        return ExecutionResult(
            success=result.success,
            action="mouse_drag",
            description="鼠标拖拽",
            data={"from": (start_x, start_y), "to": (end_x, end_y)},
            feedback=f"✅ 已从 ({start_x}, {start_y}) 拖拽到 ({end_x}, {end_y})" if result.success else f"❌ 拖拽失败: {result.message}"
        )
    
    async def _execute_mouse_scroll(self, params: Dict[str, Any]) -> ExecutionResult:
        """执行鼠标滚动"""
        clicks = params.get("clicks", 1)
        direction = params.get("direction", "down")
        
        scroll_clicks = -abs(clicks) if direction == "up" else abs(clicks)
        result = self.mouse.scroll(clicks=scroll_clicks)
        
        dir_desc = "向下" if direction == "down" else "向上"
        
        return ExecutionResult(
            success=result.success,
            action="mouse_scroll",
            description="鼠标滚动",
            data={"clicks": clicks, "direction": direction},
            feedback=f"✅ 已{dir_desc}滚动 {abs(clicks)} 次" if result.success else f"❌ 滚动失败: {result.message}"
        )
    
    async def _execute_mouse_position(self, params: Dict[str, Any]) -> ExecutionResult:
        """获取鼠标位置"""
        result = self.mouse.get_position()
        
        return ExecutionResult(
            success=True,
            action="mouse_position",
            description="获取鼠标位置",
            data={"x": result.x, "y": result.y},
            feedback=f"✅ 当前鼠标位置: ({result.x}, {result.y})"
        )
    
    # ==================== 键盘操作 ====================
    
    async def _execute_keyboard_type(self, params: Dict[str, Any]) -> ExecutionResult:
        """执行键盘输入"""
        text = params.get("text", "")
        interval = params.get("interval", 0.05)
        
        result = self.keyboard.type_text(text, interval=interval)
        
        return ExecutionResult(
            success=result.success,
            action="keyboard_type",
            description="键盘输入",
            data={"text": text[:50] + "..." if len(text) > 50 else text},
            feedback=f"✅ 已输入文本: \"{text[:20]}{'...' if len(text) > 20 else ''}\"" if result.success else f"❌ 输入失败: {result.message}"
        )
    
    async def _execute_keyboard_press(self, params: Dict[str, Any]) -> ExecutionResult:
        """执行按键"""
        key = params.get("key", "")
        
        result = self.keyboard.press(key)
        
        return ExecutionResult(
            success=result.success,
            action="keyboard_press",
            description="按下按键",
            data={"key": key},
            feedback=f"✅ 已按下 {key} 键" if result.success else f"❌ 按键失败: {result.message}"
        )
    
    async def _execute_keyboard_hotkey(self, params: Dict[str, Any]) -> ExecutionResult:
        """执行组合键"""
        keys = params.get("keys", [])
        
        result = self.keyboard.hotkey(*keys)
        
        keys_str = "+".join(keys)
        
        return ExecutionResult(
            success=result.success,
            action="keyboard_hotkey",
            description="执行组合键",
            data={"keys": keys},
            feedback=f"✅ 已执行组合键: {keys_str}" if result.success else f"❌ 组合键失败: {result.message}"
        )
    
    # ==================== 窗口操作 ====================
    
    async def _execute_window_list(self, params: Dict[str, Any]) -> ExecutionResult:
        """列出窗口"""
        result = self.window.list_windows()
        
        window_titles = [w.title for w in result[:10]]
        
        return ExecutionResult(
            success=True,
            action="window_list",
            description="列出窗口",
            data={"count": len(result), "windows": window_titles},
            feedback=f"✅ 找到 {len(result)} 个窗口"
        )
    
    async def _execute_window_active(self, params: Dict[str, Any]) -> ExecutionResult:
        """获取活动窗口"""
        result = self.window.get_active_window()
        
        return ExecutionResult(
            success=result is not None,
            action="window_active",
            description="获取活动窗口",
            data={"title": result.title, "handle": result.handle} if result else None,
            feedback=f"✅ 活动窗口: {result.title}" if result else "❌ 获取活动窗口失败"
        )
    
    async def _execute_window_activate(self, params: Dict[str, Any]) -> ExecutionResult:
        """激活窗口"""
        title = params.get("title", "")
        
        windows = self.window.list_windows()
        target = None
        for w in windows:
            if title.lower() in w.title.lower():
                target = w
                break
        
        if not target:
            return ExecutionResult(
                success=False,
                action="window_activate",
                description="激活窗口",
                error=f"未找到包含 '{title}' 的窗口",
                feedback=f"❌ 未找到包含 '{title}' 的窗口"
            )
        
        result = self.window.activate_window(target.handle)
        
        return ExecutionResult(
            success=result.success,
            action="window_activate",
            description="激活窗口",
            data={"title": target.title},
            feedback=f"✅ 已激活窗口: {target.title}" if result.success else f"❌ 激活失败: {result.message}"
        )
    
    async def _execute_window_close(self, params: Dict[str, Any]) -> ExecutionResult:
        """关闭窗口"""
        title = params.get("title", "")
        
        windows = self.window.list_windows()
        target = None
        for w in windows:
            if title.lower() in w.title.lower():
                target = w
                break
        
        if not target:
            return ExecutionResult(
                success=False,
                action="window_close",
                description="关闭窗口",
                error=f"未找到包含 '{title}' 的窗口",
                feedback=f"❌ 未找到包含 '{title}' 的窗口"
            )
        
        result = self.window.close_window(target.handle)
        
        return ExecutionResult(
            success=result.success,
            action="window_close",
            description="关闭窗口",
            data={"title": target.title},
            feedback=f"✅ 已关闭窗口: {target.title}" if result.success else f"❌ 关闭失败: {result.message}"
        )
    
    async def _execute_window_minimize(self, params: Dict[str, Any]) -> ExecutionResult:
        """最小化窗口"""
        title = params.get("title", "")
        
        windows = self.window.list_windows()
        target = None
        for w in windows:
            if title.lower() in w.title.lower():
                target = w
                break
        
        if not target:
            return ExecutionResult(
                success=False,
                action="window_minimize",
                description="最小化窗口",
                error=f"未找到包含 '{title}' 的窗口",
                feedback=f"❌ 未找到包含 '{title}' 的窗口"
            )
        
        result = self.window.minimize_window(target.handle)
        
        return ExecutionResult(
            success=result.success,
            action="window_minimize",
            description="最小化窗口",
            data={"title": target.title},
            feedback=f"✅ 已最小化窗口: {target.title}" if result.success else f"❌ 最小化失败: {result.message}"
        )
    
    async def _execute_window_maximize(self, params: Dict[str, Any]) -> ExecutionResult:
        """最大化窗口"""
        title = params.get("title", "")
        
        windows = self.window.list_windows()
        target = None
        for w in windows:
            if title.lower() in w.title.lower():
                target = w
                break
        
        if not target:
            return ExecutionResult(
                success=False,
                action="window_maximize",
                description="最大化窗口",
                error=f"未找到包含 '{title}' 的窗口",
                feedback=f"❌ 未找到包含 '{title}' 的窗口"
            )
        
        result = self.window.maximize_window(target.handle)
        
        return ExecutionResult(
            success=result.success,
            action="window_maximize",
            description="最大化窗口",
            data={"title": target.title},
            feedback=f"✅ 已最大化窗口: {target.title}" if result.success else f"❌ 最大化失败: {result.message}"
        )
    
    # ==================== OCR 操作 ====================
    
    async def _execute_ocr_recognize(self, params: Dict[str, Any]) -> ExecutionResult:
        """OCR 识别"""
        from PIL import Image
        import io
        import base64
        
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
        
        return ExecutionResult(
            success=True,
            action="ocr_recognize",
            description="OCR 识别",
            data={"text": text[:500]},
            feedback=f"✅ OCR 识别完成，识别到 {len(text)} 个字符"
        )
    
    async def _execute_ocr_find_text(self, params: Dict[str, Any]) -> ExecutionResult:
        """查找文本"""
        from PIL import Image
        import io
        import base64
        
        text = params.get("text", "")
        
        screenshot = self.screen.capture_screen()
        image = Image.open(io.BytesIO(base64.b64decode(screenshot.base64)))
        
        result = self.ocr.find_text(image, text)
        
        found = result.found if hasattr(result, 'found') else False
        position = result.position if hasattr(result, 'position') else None
        
        return ExecutionResult(
            success=True,
            action="ocr_find_text",
            description="查找文本",
            data={"text": text, "found": found, "position": position},
            feedback=f"✅ 找到文本 \"{text}\" 在位置 {position}" if found else f"❌ 未找到文本: {text}"
        )
    
    # ==================== 录制操作 ====================
    
    async def _execute_record_start(self, params: Dict[str, Any]) -> ExecutionResult:
        """开始录制"""
        try:
            self.recorder.start_recording()
            return ExecutionResult(
                success=True,
                action="record_start",
                description="开始录制",
                feedback="✅ 开始录制操作"
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                action="record_start",
                description="开始录制",
                error=str(e),
                feedback=f"❌ 启动录制失败: {str(e)}"
            )
    
    async def _execute_record_stop(self, params: Dict[str, Any]) -> ExecutionResult:
        """停止录制"""
        try:
            actions = self.recorder.stop_recording()
            return ExecutionResult(
                success=True,
                action="record_stop",
                description="停止录制",
                data={"action_count": len(actions)},
                feedback=f"✅ 录制完成，共录制 {len(actions)} 个操作"
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                action="record_stop",
                description="停止录制",
                error=str(e),
                feedback=f"❌ 停止录制失败: {str(e)}"
            )
    
    async def _execute_record_play(self, params: Dict[str, Any]) -> ExecutionResult:
        """回放操作"""
        speed = params.get("speed", 1.0)
        
        try:
            self.recorder.play(speed=speed)
            return ExecutionResult(
                success=True,
                action="record_play",
                description="回放操作",
                data={"speed": speed},
                feedback="✅ 回放完成"
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                action="record_play",
                description="回放操作",
                error=str(e),
                feedback=f"❌ 回放失败: {str(e)}"
            )
    
    # ==================== 降级处理方法 ====================
    
    def _fallback_screenshot(self, params: Dict[str, Any]) -> ExecutionResult:
        """截图降级方案：使用系统命令"""
        import subprocess
        import tempfile
        import os
        
        try:
            temp_path = tempfile.mktemp(suffix=".png")
            
            if os.name == "nt":
                import mss
                with mss.mss() as sct:
                    sct.shot(output=temp_path)
            else:
                subprocess.run(["scrot", temp_path], check=True)
            
            return ExecutionResult(
                success=True,
                action="screenshot",
                description="截图（降级模式）",
                data={"path": temp_path, "fallback": True},
                feedback="✅ 截图完成（使用降级模式）"
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                action="screenshot",
                description="截图",
                error=str(e),
                feedback=f"❌ 截图失败（降级模式也失败）: {str(e)}。建议安装 mss 库: pip install mss"
            )
    
    def _fallback_mouse_click(self, params: Dict[str, Any]) -> ExecutionResult:
        """鼠标点击降级方案"""
        x = params.get("x", 0)
        y = params.get("y", 0)
        
        return ExecutionResult(
            success=False,
            action="mouse_click",
            description="鼠标点击",
            error="鼠标控制不可用",
            feedback=f"❌ 鼠标控制功能不可用。建议安装 pyautogui: pip install pyautogui"
        )
    
    def _fallback_mouse_move(self, params: Dict[str, Any]) -> ExecutionResult:
        """鼠标移动降级方案"""
        return ExecutionResult(
            success=False,
            action="mouse_move",
            description="鼠标移动",
            error="鼠标控制不可用",
            feedback=f"❌ 鼠标控制功能不可用。建议安装 pyautogui: pip install pyautogui"
        )
    
    def _fallback_keyboard_type(self, params: Dict[str, Any]) -> ExecutionResult:
        """键盘输入降级方案"""
        return ExecutionResult(
            success=False,
            action="keyboard_type",
            description="键盘输入",
            error="键盘控制不可用",
            feedback=f"❌ 键盘控制功能不可用。建议安装 pyautogui: pip install pyautogui"
        )
    
    def _fallback_window_list(self, params: Dict[str, Any]) -> ExecutionResult:
        """窗口列表降级方案：使用系统命令"""
        import subprocess
        
        try:
            if os.name == "nt":
                result = subprocess.run(
                    ["powershell", "-Command", "Get-Process | Where-Object {$_.MainWindowTitle} | Select-Object ProcessName, MainWindowTitle | ConvertTo-Json"],
                    capture_output=True,
                    text=True
                )
            else:
                result = subprocess.run(["wmctrl", "-l"], capture_output=True, text=True)
            
            return ExecutionResult(
                success=True,
                action="window_list",
                description="列出窗口（降级模式）",
                data={"output": result.stdout, "fallback": True},
                feedback="✅ 窗口列表获取完成（使用降级模式）"
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                action="window_list",
                description="列出窗口",
                error=str(e),
                feedback=f"❌ 窗口列表获取失败。建议安装 pywin32 (Windows) 或 wmctrl (Linux)"
            )
    
    def _fallback_ocr(self, params: Dict[str, Any]) -> ExecutionResult:
        """OCR降级方案"""
        return ExecutionResult(
            success=False,
            action="ocr_recognize",
            description="OCR识别",
            error="OCR功能不可用",
            feedback=f"❌ OCR识别功能不可用。建议安装 tesseract 和 pytesseract: pip install pytesseract"
        )


_cua_executor: Optional[CUAExecutor] = None


def get_cua_executor() -> CUAExecutor:
    """获取 CUA 执行器单例"""
    global _cua_executor
    if _cua_executor is None:
        _cua_executor = CUAExecutor()
    return _cua_executor
