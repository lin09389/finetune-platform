import sys
sys.path.insert(0, 'server')

from core.config import get_settings
from pathlib import Path

s = get_settings()
print(f"models_dir: {s.models_dir}")
print(f"base_dir: {s.base_dir}")
print(f"models_dir_resolved: {s.models_dir_resolved}")
print(f"exists: {s.models_dir_resolved.exists()}")

# 列出模型目录内容
if s.models_dir_resolved.exists():
    print("\n模型目录内容:")
    for item in s.models_dir_resolved.iterdir():
        print(f"  - {item.name} ({'dir' if item.is_dir() else 'file'})")
        if item.is_dir():
            for sub in item.iterdir():
                print(f"    - {sub.name}")