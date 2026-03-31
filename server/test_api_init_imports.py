import sys

server_path = r'c:\Users\JHJ\Desktop\finetune-platform\server'
sys.path.insert(0, server_path)

# Modules imported by api/__init__.py
imports = [
    'api.device',
    'api.models',
    'api.datasets',
    'api.training',
    'api.workspace',
    'api.model_center',
    'api.agent',
    'api.context',
    'api.cloud_chat',
    'api.skills',
    'api.cua',
    'api.mcp',
    'api.gateway_api.routes',
    'api.inference',
    'api.chat',
    'api.knowledge',
    'api.memory_new',
]

print("Testing imports from api/__init__.py...")

for mod in imports:
    try:
        __import__(mod)
        print(f'  [OK] {mod}')
    except Exception as e:
        print(f'  [FAIL] {mod}: {str(e)[:80]}')
