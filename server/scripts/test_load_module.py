import importlib.util
import os
import sys

# Add server to path
server_path = r'c:\Users\JHJ\Desktop\finetune-platform\server'
sys.path.insert(0, server_path)

# Test loading api.errors directly
filepath = os.path.join(server_path, 'api', 'errors.py')
print(f'Loading: {filepath}')
print(f'Exists: {os.path.exists(filepath)}')
print(f'Size: {os.path.getsize(filepath)} bytes')

# Read file content
with open(filepath, 'rb') as f:
    content = f.read()

print(f'Content length: {len(content)}')
print(f'First 50 bytes: {content[:50]}')

# Try to decode
try:
    text = content.decode('utf-8')
    print(f'Decoded length: {len(text)} chars')
    print(f'First 100 chars: {text[:100]}')
except UnicodeDecodeError as e:
    print(f'Decode error: {e}')

# Try to load as module
spec = importlib.util.spec_from_file_location("api.errors", filepath)
if spec and spec.loader:
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        print('Module loaded successfully!')
        print(f'Module has APIError: {hasattr(module, "APIError")}')
    except Exception as e:
        print(f'Module load error: {e}')
