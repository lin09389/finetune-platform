# -*- coding: utf-8 -*-
import os

api_dir = r'c:\Users\JHJ\Desktop\finetune-platform\server\api'

# List all .py files and try to decode
for f in sorted(os.listdir(api_dir)):
    if f.endswith('.py'):
        filepath = os.path.join(api_dir, f)
        with open(filepath, 'rb') as file:
            data = file.read()
        
        # Try to decode
        try:
            text = data.decode('utf-8')
            print(f'[OK] {f}: {len(text)} chars')
        except UnicodeDecodeError as e:
            print(f'[FAIL] {f}: {e}')
