import os
import sys

server_dir = r'c:\Users\JHJ\Desktop\finetune-platform\server'
sys.path.insert(0, server_dir)

api_dir = os.path.join(server_dir, 'api')

for root, _dirs, files in os.walk(api_dir):
    for f in files:
        if f.endswith('.py'):
            filepath = os.path.join(root, f)
            try:
                with open(filepath, encoding='utf-8') as file:
                    content = file.read()
                print(f"OK: {filepath}")
            except UnicodeDecodeError as e:
                print(f"FAIL: {filepath}")
                print(f"  Error: {e}")
                with open(filepath, 'rb') as file:
                    data = file.read()
                print(f"  First 50 bytes: {data[:50]}")
            except Exception as e:
                print(f"ERROR: {filepath} - {e}")
