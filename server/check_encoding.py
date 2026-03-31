import os
import sys

server_dir = r'c:\Users\JHJ\Desktop\finetune-platform\server'
sys.path.insert(0, server_dir)

files_to_check = [
    'api/device.py',
    'api/models.py',
    'api/datasets.py',
    'api/training.py',
    'api/workspace.py',
    'api/model_center.py',
    'api/agent.py',
    'api/context.py',
    'api/cloud_chat.py',
    'api/skills.py',
    'api/cua.py',
    'api/mcp.py',
    'api/gateway_api/routes.py',
    'api/inference/__init__.py',
    'api/chat.py',
    'api/knowledge.py',
    'api/memory_new.py',
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
