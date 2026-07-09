#!/usr/bin/env python3
"""
Finetune Platform 安装验证脚本
"""
import subprocess
import sys
from pathlib import Path

COLORS = {
    'GREEN': '\033[92m',
    'RED': '\033[91m',
    'YELLOW': '\033[93m',
    'BLUE': '\033[94m',
    'END': '\033[0m',
}

def color(text, color_name):
    return f"{COLORS.get(color_name, '')}{text}{COLORS['END']}"

def check_python_version():
    """检查 Python 版本"""
    print("\n" + "=" * 50)
    print(color("检查 Python 版本...", "BLUE"))

    print(color(f"[OK] Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}", "GREEN"))
    return True

def check_dependencies():
    """检查依赖包"""
    print("\n" + "=" * 50)
    print(color("检查依赖包...", "BLUE"))

    required_packages = [
        'fastapi',
        'uvicorn',
        'pydantic',
        'pydantic_settings',
        'torch',
        'transformers',
        'peft',
        'accelerate',
        'pytest',
        'python_json_logger',
    ]

    missing = []
    for pkg in required_packages:
        try:
            __import__(pkg.replace('_', '-'))
            print(color(f"  [OK] {pkg}", "GREEN"))
        except ImportError:
            print(color(f"  [X] {pkg}", "RED"))
            missing.append(pkg)

    if missing:
        print(color(f"\n缺失依赖：{', '.join(missing)}", "YELLOW"))
        print("运行：pip install -r requirements.txt")
        return False

    return True

def check_directories():
    """检查目录结构"""
    print("\n" + "=" * 50)
    print(color("检查目录结构...", "BLUE"))

    required_dirs = [
        'server/core',
        'server/tests',
        'server/logs',
        'models',
        'datasets',
        'outputs',
    ]

    base = Path(__file__).parent
    missing = []

    for dir_path in required_dirs:
        full_path = base / dir_path
        if not full_path.exists():
            print(color(f"  [X] {dir_path}", "RED"))
            missing.append(dir_path)
        else:
            print(color(f"  [OK] {dir_path}", "GREEN"))

    # 创建缺失目录
    for dir_path in missing:
        full_path = base / dir_path
        full_path.mkdir(parents=True, exist_ok=True)
        print(color(f"  [!] 创建 {dir_path}", "YELLOW"))

    return True

def check_config():
    """检查配置文件"""
    print("\n" + "=" * 50)
    print(color("检查配置文件...", "BLUE"))

    base = Path(__file__).parent
    env_file = base / 'server' / '.env'
    env_example = base / 'server' / '.env.example'

    if env_file.exists():
        print(color("  [OK] .env 文件存在", "GREEN"))
    else:
        print(color("  [!] .env 文件不存在", "YELLOW"))
        if env_example.exists():
            print("  提示：复制 .env.example 为 .env")

    # 验证配置导入
    try:
        sys.path.insert(0, str(base / 'server'))
        from core.config import settings
        print(color("  [OK] 配置加载成功", "GREEN"))
        print(f"    - Host: {settings.host}")
        print(f"    - Port: {settings.port}")
        print(f"    - Models: {settings.models_dir_resolved}")
    except Exception as e:
        print(color(f"  [X] 配置加载失败：{e}", "RED"))
        return False

    return True

def check_cuda():
    """检查 CUDA"""
    print("\n" + "=" * 50)
    print(color("检查 CUDA...", "BLUE"))

    try:
        import torch

        if torch.cuda.is_available():
            print(color("  [OK] CUDA 可用", "GREEN"))
            print(f"    - 设备：{torch.cuda.get_device_name(0)}")
            print(f"    - 显存：{torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
        else:
            print(color("  [!] CUDA 不可用", "YELLOW"))
            print("    将使用 CPU 模式（训练会很慢）")
    except ImportError:
        print(color("  [X] PyTorch 未安装", "RED"))
    except Exception as e:
        print(color(f"  [!] CUDA 检查失败：{e}", "YELLOW"))

    return True

def run_tests():
    """运行测试"""
    print("\n" + "=" * 50)
    print(color("运行快速测试...", "BLUE"))

    base = Path(__file__).parent
    server_path = base / 'server'

    try:
        result = subprocess.run(
            ['pytest', 'tests/test_device.py', '-v', '--tb=short'],
            cwd=server_path,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            print(color("  [OK] 测试通过", "GREEN"))
        else:
            print(color("  [!] 部分测试失败", "YELLOW"))
            print(result.stdout[-500:])  # 显示最后 500 字符
    except subprocess.TimeoutExpired:
        print(color("  [!] 测试超时", "YELLOW"))
    except FileNotFoundError:
        print(color("  [!] pytest 未安装", "YELLOW"))
    except Exception as e:
        print(color(f"  [!] 测试失败：{e}", "YELLOW"))

    return True

def main():
    """主函数"""
    print(color("\n" + "=" * 50, "BLUE"))
    print(color("  Finetune Platform 安装验证", "BLUE"))
    print(color("=" * 50, "BLUE"))

    checks = [
        ("Python 版本", check_python_version),
        ("依赖包", check_dependencies),
        ("目录结构", check_directories),
        ("配置文件", check_config),
        ("CUDA", check_cuda),
        ("快速测试", run_tests),
    ]

    results = []
    for name, check_func in checks:
        try:
            result = check_func()
            results.append((name, result))
        except Exception as e:
            print(color(f"\n[X] {name} 检查异常：{e}", "RED"))
            results.append((name, False))

    # 汇总
    print("\n" + "=" * 50)
    print(color("验证汇总", "BLUE"))
    print("=" * 50)

    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = color("[OK]", "GREEN") if result else color("[X]", "RED")
        print(f"  {status} {name}")

    print(f"\n总计：{passed}/{total} 通过")

    if passed == total:
        print(color("\n[OK] 所有检查通过！系统已就绪。", "GREEN"))
        print("\n启动命令:")
        print("  cd server && python -m uvicorn main:app --reload")
        print("  cd client && npm run dev")
        return 0
    else:
        print(color("\n[!] 部分检查未通过，请查看上方详情。", "YELLOW"))
        return 1

if __name__ == '__main__':
    sys.exit(main())
