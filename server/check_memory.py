import os
import sys

server_dir = r'c:\Users\JHJ\Desktop\finetune-platform\server'
sys.path.insert(0, server_dir)

files_to_check = [
    'memory/__init__.py',
    'memory/service.py',
    'memory/memory_service.py',
    'memory/memory_extractor.py',
    'memory/models.py',
]

for f in files_to_check:
    path = os.path.join(server_dir, f)
    if os.path.exists(path):
        try:
            with open(path, encoding='utf-8') as file:
                content = file.read()
            print(f"OK: {f}")
        except UnicodeDecodeError as e:
            print(f"FAIL: {f} - {e}")
        except Exception as e:
            print(f"ERROR: {f} - {e}")
    else:
        print(f"NOT FOUND: {f}")
