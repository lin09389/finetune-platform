# CUA (Computer Use Agent) 模块使用文档

## 概述

CUA 模块提供计算机操作自动化能力，包括屏幕捕获、鼠标控制、键盘输入、窗口管理、OCR 识别等功能。

## 安装依赖

```bash
pip install mss pillow pyautogui pyperclip pytesseract opencv-python numpy pygetwindow pynput
```

## 快速开始

### 1. 屏幕截图

```python
from cua import ScreenCapture

capture = ScreenCapture()

# 截取整个屏幕
result = capture.capture_screen(monitor=0)
print(f"截图尺寸: {result.width}x{result.height}")
print(f"Base64 长度: {len(result.image_base64)}")

# 截取指定区域
from cua import Region
region = Region(x=0, y=0, width=800, height=600)
result = capture.capture_region(region)

# 获取显示器数量
count = capture.get_monitor_count()
print(f"显示器数量: {count}")
```

### 2. 鼠标操作

```python
from cua import MouseController, MouseButton

mouse = MouseController()

# 获取当前位置
pos = mouse.get_position()
print(f"鼠标位置: {pos.x}, {pos.y}")

# 移动鼠标
mouse.move_to(500, 300, duration=0.5)

# 点击
mouse.click(500, 300, button=MouseButton.LEFT, clicks=1)

# 双击
mouse.double_click(500, 300)

# 右键点击
mouse.right_click(500, 300)

# 拖拽
mouse.drag(100, 100, 500, 300, duration=1.0)

# 滚动
mouse.scroll(clicks=3)  # 向上滚动
mouse.scroll(clicks=-3)  # 向下滚动
```

### 3. 键盘操作

```python
from cua import KeyboardController

keyboard = KeyboardController()

# 输入文本（支持中文）
keyboard.type_text("你好，世界！", interval=0.05)

# 按下单个键
keyboard.press("enter")

# 组合键
keyboard.hotkey("ctrl", "c")  # 复制
keyboard.hotkey("ctrl", "v")  # 粘贴
keyboard.hotkey("alt", "tab")  # 切换窗口

# 常用快捷键
keyboard.copy()
keyboard.paste()
keyboard.select_all()
keyboard.undo()
keyboard.redo()
```

### 4. 窗口管理

```python
from cua import WindowManager

window = WindowManager()

# 列出所有窗口
windows = window.list_windows()
for w in windows:
    print(f"窗口: {w.title} ({w.width}x{w.height})")

# 获取活动窗口
active = window.get_active_window()
print(f"活动窗口: {active.title}")

# 激活窗口
window.activate_window("window_id")

# 最小化/最大化/关闭
window.minimize_window("window_id")
window.maximize_window("window_id")
window.close_window("window_id")

# 移动和调整窗口
window.move_window("window_id", 100, 100)
window.resize_window("window_id", 800, 600)
```

### 5. OCR 识别

```python
from cua import OCRRecognizer
from PIL import Image

ocr = OCRRecognizer()

# 识别图像中的文本
image = Image.open("screenshot.png")
text = ocr.recognize(image, lang="chi_sim+eng")
print(f"识别结果: {text}")

# 查找文本位置
positions = ocr.find_text(image, "确定", lang="chi_sim+eng")
for pos in positions:
    print(f"找到文本位置: {pos.x}, {pos.y}")

# 获取所有文本框
boxes = ocr.get_text_boxes(image)
for box in boxes:
    print(f"文本: {box['text']}, 位置: {box['bbox']}")
```

### 6. 视觉识别

```python
from cua import VisionRecognizer
from PIL import Image

vision = VisionRecognizer()

# 模板匹配
screen = Image.open("screen.png")
template = Image.open("button.png")
positions = vision.find_template(screen, template, threshold=0.8)

# 查找颜色
positions = vision.find_color(screen, (255, 0, 0), tolerance=10)

# 图像相似度
similarity = vision.compare_images(image1, image2)
print(f"相似度: {similarity:.2%}")

# 等待元素出现
position = vision.wait_for_template(template, timeout=10.0)
```

### 7. 操作录制与回放

```python
from cua import ActionRecorder, ActionPlayer

# 录制操作
recorder = ActionRecorder()
recorder.start_recording()

# ... 执行一些操作 ...

recorder.stop_recording()
actions = recorder.get_actions()
print(f"录制了 {len(actions)} 个操作")

# 保存录制
recorder.save_to_file("recorded_actions.json")

# 回放操作
player = ActionPlayer()
player.play(actions, speed=1.0)

# 从文件回放
player.play_from_file("recorded_actions.json")
```

### 8. 安全控制

```python
from cua import SafetyController, PermissionLevel

safety = SafetyController()

# 设置权限级别
safety.set_permission_level(PermissionLevel.INTERACTIVE)

# 检查权限
from cua import OperationType
can_click = safety.check_permission(OperationType.MOUSE_CLICK)

# 检测敏感操作
is_sensitive = safety.is_sensitive_operation(
    OperationType.KEYBOARD_TYPE,
    {"text": "format c:"}
)

# 启用/禁用 FAILSAFE
safety.enable_failsafe(True)

# 获取审计日志
logs = safety.get_audit_logs(limit=100)
```

## 使用 Skills

CUA 功能已集成为 Skills，可直接调用：

```python
from skills.implemented.cua_skills import (
    ScreenshotSkill,
    MouseClickSkill,
    KeyboardTypeSkill,
    FindTextSkill,
    ClickTextSkill,
)

# 截图
skill = ScreenshotSkill()
result = await skill.execute(monitor=0)
print(result.data["image_base64"])

# 点击
skill = MouseClickSkill()
result = await skill.execute(x=500, y=300, button="left")

# 输入文本
skill = KeyboardTypeSkill()
result = await skill.execute(text="你好世界", interval=0.05)

# 查找并点击文本
skill = ClickTextSkill()
result = await skill.execute(text="确定", lang="chi_sim+eng")
```

## API 端点

通过 HTTP API 调用 CUA 功能：

```bash
# 屏幕截图
curl -X POST http://localhost:8000/cua/screenshot \
  -H "Content-Type: application/json" \
  -d '{"monitor": 0}'

# 鼠标点击
curl -X POST http://localhost:8000/cua/mouse/click \
  -H "Content-Type: application/json" \
  -d '{"x": 500, "y": 300, "button": "left"}'

# 键盘输入
curl -X POST http://localhost:8000/cua/keyboard/type \
  -H "Content-Type: application/json" \
  -d '{"text": "你好世界"}'

# 窗口列表
curl http://localhost:8000/cua/window/list

# OCR 识别
curl -X POST http://localhost:8000/cua/ocr \
  -H "Content-Type: application/json" \
  -d '{"lang": "chi_sim+eng"}'
```

## 配置选项

通过环境变量配置 CUA：

```bash
# 启用/禁用 CUA
CUA_ENABLED=true

# 权限级别: read_only, interactive, full_control
CUA_PERMISSION_LEVEL=interactive

# 截图质量 (1-100)
CUA_SCREENSHOT_QUALITY=85

# 鼠标移动速度
CUA_MOUSE_SPEED=0.5

# 键盘输入延迟
CUA_KEYBOARD_DELAY=0.05

# 操作超时时间（秒）
CUA_OPERATION_TIMEOUT=30

# 启用 FAILSAFE
CUA_FAILSAFE_ENABLED=true

# 启用审计日志
CUA_AUDIT_ENABLED=true
```

## 安全注意事项

1. **权限分级**：默认为 `interactive` 级别，只允许基本操作
2. **FAILSAFE**：启用后，移动鼠标到屏幕左上角可紧急停止
3. **敏感操作检测**：自动检测危险命令并提示确认
4. **审计日志**：记录所有操作以便追溯

## 故障排除

### 截图失败
- 确保已安装 `mss` 和 `PIL`
- 检查显示器索引是否正确

### 中文输入失败
- 使用 `pyperclip` 进行剪贴板输入
- 确保输入法处于英文模式

### OCR 识别不准
- 安装 Tesseract OCR
- 下载中文语言包 `chi_sim`
- 调整图像预处理参数

### 鼠标操作不精确
- 检查屏幕缩放比例
- 使用 `duration` 参数控制移动速度
