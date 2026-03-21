# -*- coding: utf-8 -*-
import sys
import os

server_path = r'c:\Users\JHJ\Desktop\finetune-platform\server'
sys.path.insert(0, server_path)

# Check sys.path for api directories
print("Checking sys.path for 'api' directories:")
for p in sys.path:
    api_path = os.path.join(p, 'api') if p else None
    if api_path and os.path.exists(api_path):
        print(f'  Found: {api_path}')
        if os.path.isdir(api_path):
            print(f'    Is directory')
            init_file = os.path.join(api_path, '__init__.py')
            if os.path.exists(init_file):
                print(f'    Has __init__.py: {os.path.getsize(init_file)} bytes')

# Check for api.py file
print("\nChecking for api.py files:")
for p in sys.path:
    if p:
        api_file = os.path.join(p, 'api.py')
        if os.path.exists(api_file):
            print(f'  Found: {api_file}')

# Try importing
print("\nTrying to import api package:")
try:
    import api
    print(f'  Success! api.__file__ = {api.__file__}')
except Exception as e:
    print(f'  Failed: {e}')
    
    # Try to get more details
    import traceback
    print("\nFull traceback:")
    traceback.print_exc()
