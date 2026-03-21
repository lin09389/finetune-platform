# -*- coding: utf-8 -*-
import sys
import os

server_path = r'c:\Users\JHJ\Desktop\finetune-platform\server'
sys.path.insert(0, server_path)

print("Testing import api.errors...")

# First, try to import api package
print("\n1. Import api package:")
try:
    import api
    print(f"   api.__file__ = {api.__file__}")
    print(f"   api.__path__ = {api.__path__}")
except Exception as e:
    print(f"   FAIL: {e}")

# Then try to import api.errors
print("\n2. Import api.errors:")
try:
    import api.errors
    print(f"   api.errors.__file__ = {api.errors.__file__}")
except Exception as e:
    print(f"   FAIL: {e}")

# Try direct import
print("\n3. Direct import using importlib:")
import importlib.util
filepath = os.path.join(server_path, 'api', 'errors.py')
spec = importlib.util.spec_from_file_location("api.errors", filepath)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print(f"   SUCCESS: {module}")
print(f"   Has APIError: {hasattr(module, 'APIError')}")
