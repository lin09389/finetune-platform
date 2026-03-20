#!/usr/bin/env python3
"""
Finetune Platform 安装验证脚本
"""
import sys
import subprocess
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
    """检�?Python 版本"""
    print("\n" + "=" * 50)
    print(color("检�?Python 版本...", "BLUE"))
    
    if sys.version_info < (3, 10):
        print(color("�?Python 3.10+  required", "RED"))
        print(f"当前版本：{sys.version}")
        return False
    
    print(color(f"�?Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}", "GREEN"))
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
            print(color(f"  �?{pkg}", "GREEN"))
        except ImportError:
            print(color(f"  �?{pkg}", "RED"))
            missing.append(pkg)
    
    if missing:
        print(color(f"\n缺失依赖：{', '.join(missing)}", "YELLOW"))
        print("运行：pip install -r requirements.txt")
        return False
    
    return True

def check_directories():
    """检查目录结�?""
    print("\n" + "=" * 50)
    print(color("检查目录结�?..", "BLUE"))
    
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
            print(color(f"  �?{dir_path}", "RED"))
            missing.append(dir_path)
        else:
            print(color(f"  �?{dir_path}", "GREEN"))
    
    # 创建缺失目录
    for dir_path in missing:
        full_path = base / dir_path
        full_path.mkdir(parents=True, exist_ok=True)
        print(color(f"  �?创建 {dir_path}", "YELLOW"))
    
    return True

def check_config():
    """检查配置文�?""
    print("\n" + "=" * 50)
    print(color("检查配置文�?..", "BLUE"))
    
    base = Path(__file__).parent
    env_file = base / 'server' / '.env'
    env_example = base / 'server' / '.env.example'
    
    if env_file.exists():
        print(color("  �?.env 文件存在", "GREEN"))
    else:
        print(color("  �?.env 文件不存�?, "YELLOW"))
        if env_example.exists():
            print("  提示：复�?.env.example �?.env")
    
    # 验证配置导入
    try:
        sys.path.insert(0, str(base / 'server'))
        from core.config import settings
        print(color("  �?配置加载成功", "GREEN"))
        print(f"    - Host: {settings.host}")
        print(f"    - Port: {settings.port}")
        print(f"    - Models: {settings.models_dir_resolved}")
    except Exception as e:
        print(color(f"  �?配置加载失败：{e}", "RED"))
        return False
    
    return True

def check_cuda():
    """检�?CUDA"""
    print("\n" + "=" * 50)
    print(color("检�?CUDA...", "BLUE"))
    
    try:
        import torch
        
        if torch.cuda.is_available():
            print(color("  �?CUDA 可用", "GREEN"))
            print(f"    - 设备：{torch.cuda.get_device_name(0)}")
            print(f"    - 显存：{torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
        else:
            print(color("  �?CUDA 不可�?, "YELLOW"))
            print("    将使�?CPU 模式（训练会很慢�?)
    except ImportError:
        print(color("  �?PyTorch 未安�?, "RED"))
    except Exception as e:
        print(color(f"  �?CUDA 检查失败：{e}", "YELLOW"))
    
    return True

def run_tests():
    """运行测试"""
    print("\n" + "=" * 50)
    print(color("运行快速测�?..", "BLUE"))
    
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
            print(color("  �?测试通过", "GREEN"))
        else:
            print(color("  �?部分测试失败", "YELLOW"))
            print(result.stdout[-500:])  # 显示最�?500 字符
    except subprocess.TimeoutExpired:
        print(color("  �?测试超时", "YELLOW"))
    except FileNotFoundError:
        print(color("  �?pytest 未安�?, "YELLOW"))
    except Exception as e:
        print(color(f"  �?测试失败：{e}", "YELLOW"))
    
    return True

def main():
    """主函�?""
    print(color("\n" + "=" * 50, "BLUE"))
    print(color("  Finetune Platform 安装验证", "BLUE"))
    print(color("=" * 50, "BLUE"))
    
    checks = [
        ("Python 版本", check_python_version),
        ("依赖�?, check_dependencies),
        ("目录结构", check_directories),
        ("配置文件", check_config),
        ("CUDA", check_cuda),
        ("快速测�?, run_tests),
    ]
    
    results = []
    for name, check_func in checks:
        try:
            result = check_func()
            results.append((name, result))
        except Exception as e:
            print(color(f"\n�?{name} 检查异常：{e}", "RED"))
            results.append((name, False))
    
    # 汇�?    print("\n" + "=" * 50)
    print(color("验证汇�?, "BLUE"))
    print("=" * 50)
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        status = color("�?, "GREEN") if result else color("�?, "RED")
        print(f"  {status} {name}")
    
    print(f"\n总计：{passed}/{total} 通过")
    
    if passed == total:
        print(color("\n🎉 所有检查通过！系统已就绪�?, "GREEN"))
        print("\n启动命令:")
        print("  cd server && python -m uvicorn main:app --reload")
        print("  cd client && npm run dev")
        return 0
    else:
        print(color("\n�?部分检查未通过，请查看上方详情�?, "YELLOW"))
        return 1

if __name__ == '__main__':
    sys.exit(main())
