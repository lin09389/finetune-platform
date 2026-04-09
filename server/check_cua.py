"""
CUA 模块诊断脚本
检查 CUA 功能所需的依赖是否正确安装
"""
import io
import platform
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

def print_header(title):
    print("\n" + "=" * 60)
    print(f" {title}")
    print("=" * 60)

def check_module(module_name, import_name=None, install_hint=""):
    """检查模块是否可用"""
    import_name = import_name or module_name
    try:
        __import__(import_name)
        print(f"  [OK] {module_name} - 已安装")
        return True
    except ImportError:
        print(f"  [X] {module_name} - 未安装")
        if install_hint:
            print(f"      安装命令: {install_hint}")
        return False

def check_cua_controllers():
    """检查 CUA 控制器"""
    print_header("CUA 控制器检查")

    controllers = [
        ("截图功能", "cua.screen", "ScreenCapture", "pip install mss pillow"),
        ("鼠标控制", "cua.mouse", "MouseController", "pip install pyautogui pynput"),
        ("键盘控制", "cua.keyboard", "KeyboardController", "pip install pyautogui pynput"),
        ("窗口管理", "cua.window", "WindowManager", "pip install pywin32 (Windows) 或 pyobjc (macOS)"),
        ("OCR识别", "cua.ocr", "OCRRecognizer", "pip install pytesseract pillow"),
        ("操作录制", "cua.recorder", "ActionRecorder", "pip install pynput"),
    ]

    available = 0
    for name, module, cls, hint in controllers:
        try:
            mod = __import__(module, fromlist=[cls])
            getattr(mod, cls)
            print(f"  [OK] {name} ({cls}) - 可用")
            available += 1
        except ImportError as e:
            print(f"  [X] {name} ({cls}) - 不可用")
            print(f"      错误: {e}")
            print(f"      安装: {hint}")
        except Exception as e:
            print(f"  [!] {name} ({cls}) - 初始化失败")
            print(f"      错误: {e}")

    print(f"\n  可用控制器: {available}/{len(controllers)}")
    return available

def check_tesseract():
    """检查 Tesseract OCR"""
    print_header("Tesseract OCR 检查")

    try:
        import pytesseract
        print("  [OK] pytesseract 已安装")

        try:
            version = pytesseract.get_tesseract_version()
            print(f"  [OK] Tesseract 版本: {version}")
        except Exception as e:
            print("  [X] Tesseract 未正确安装或未添加到 PATH")
            print(f"      错误: {e}")
            print("\n  安装方法:")
            if platform.system() == "Windows":
                print("      1. 下载: https://github.com/UB-Mannheim/tesseract/wiki")
                print("      2. 安装后添加到 PATH: C:\\Program Files\\Tesseract-OCR")
                print("      3. 或设置: pytesseract.pytesseract.tesseract_cmd = r'C:\\Program Files\\Tesseract-OCR\\tesseract.exe'")
            elif platform.system() == "Darwin":
                print("      brew install tesseract")
            else:
                print("      sudo apt-get install tesseract-ocr")
    except ImportError:
        print("  [X] pytesseract 未安装")
        print("      安装: pip install pytesseract")

def check_pyautogui():
    """检查 PyAutoGUI"""
    print_header("PyAutoGUI 检查")

    try:
        import pyautogui
        print("  [OK] pyautogui 已安装")

        size = pyautogui.size()
        print(f"  [OK] 屏幕尺寸: {size.width}x{size.height}")

        pos = pyautogui.position()
        print(f"  [OK] 鼠标位置: ({pos.x}, {pos.y})")

        print(f"  [i] FAILSAFE: {'启用' if pyautogui.FAILSAFE else '禁用'}")

    except ImportError:
        print("  [X] pyautogui 未安装")
        print("      安装: pip install pyautogui")
    except Exception as e:
        print(f"  [X] PyAutoGUI 错误: {e}")

def check_pynput():
    """检查 pynput"""
    print_header("pynput 检查")

    try:
        __import__("pynput")
        print("  [OK] pynput 已安装")

        if platform.system() == "Darwin":
            print("  [!] macOS 需要辅助功能权限")
            print("      系统偏好设置 -> 安全性与隐私 -> 辅助功能")
        elif platform.system() == "Linux":
            print("  [!] Linux 可能需要 X11 权限")

    except ImportError:
        print("  [X] pynput 未安装")
        print("      安装: pip install pynput")

def check_window_manager():
    """检查窗口管理器"""
    print_header("窗口管理器检查")

    system = platform.system()

    if system == "Windows":
        try:
            import win32gui
            print("  [OK] pywin32 已安装")

            hwnd = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(hwnd)
            print(f"  [OK] 活动窗口: {title}")

        except ImportError:
            print("  [X] pywin32 未安装")
            print("      安装: pip install pywin32")
    elif system == "Darwin":
        try:
            __import__("AppKit")
            print("  [OK] pyobjc 已安装")
        except ImportError:
            print("  [X] pyobjc 未安装")
            print("      安装: pip install pyobjc")
    else:
        print("  [i] Linux 窗口管理需要 ewmh 或类似工具")

def test_screenshot():
    """测试截图功能"""
    print_header("截图功能测试")

    try:
        import mss
        print("  [OK] mss 已安装")

        with mss.mss() as sct:
            monitors = sct.monitors
            print(f"  [OK] 检测到 {len(monitors) - 1} 个显示器")

            for i, mon in enumerate(monitors[1:], 1):
                print(f"      显示器 {i}: {mon['width']}x{mon['height']}")

    except ImportError:
        print("  [X] mss 未安装")
        print("      安装: pip install mss")
    except Exception as e:
        print(f"  [X] 截图测试失败: {e}")

def main():
    print("\n" + "=" * 60)
    print(" CUA (Computer Use Agent) 模块诊断")
    print(f" 系统: {platform.system()} {platform.release()}")
    print(f" Python: {sys.version}")
    print("=" * 60)

    print_header("基础模块检查")
    modules = [
        ("pyautogui", None, "pip install pyautogui"),
        ("pynput", None, "pip install pynput"),
        ("mss", None, "pip install mss"),
        ("PIL", "PIL", "pip install Pillow"),
        ("pytesseract", None, "pip install pytesseract"),
    ]

    for name, imp, hint in modules:
        check_module(name, imp, hint)

    check_pyautogui()
    check_pynput()
    check_tesseract()
    check_window_manager()
    test_screenshot()

    available = check_cua_controllers()

    print_header("诊断总结")
    if available >= 4:
        print("  [OK] CUA 模块基本可用")
        print("  可以执行: 截图、鼠标操作、键盘操作等")
        if available < 6:
            print("  [!] 部分功能不可用，请根据上述提示安装缺失的依赖")
    elif available >= 2:
        print("  [!] CUA 模块部分可用")
        print("  请安装缺失的依赖以获得完整功能")
    else:
        print("  [X] CUA 模块不可用")
        print("  请先安装必要的依赖:")
        print("      pip install pyautogui pynput mss Pillow")

    print("\n" + "=" * 60)

if __name__ == "__main__":
    main()
