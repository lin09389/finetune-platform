# -*- coding: utf-8 -*-
import os

files = [
    r'c:\Users\JHJ\Desktop\finetune-platform\server\api\errors.py',
    r'c:\Users\JHJ\Desktop\finetune-platform\server\api\ocr.py',
    r'c:\Users\JHJ\Desktop\finetune-platform\server\api\skills.py',
    r'c:\Users\JHJ\Desktop\finetune-platform\server\api\inference\routes.py',
]

for filepath in files:
    if os.path.exists(filepath):
        size = os.path.getsize(filepath)
        with open(filepath, 'rb') as f:
            data = f.read()
        print(f'{filepath}:')
        print(f'  Size: {size} bytes')
        print(f'  First 20 bytes: {data[:20]}')
        print(f'  Last 20 bytes: {data[-20:]}')
        print()
