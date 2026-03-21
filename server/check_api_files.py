# -*- coding: utf-8 -*-
import os

files_to_check = [
    r'c:\Users\JHJ\Desktop\finetune-platform\server\api\errors.py',
    r'c:\Users\JHJ\Desktop\finetune-platform\server\api\ocr.py',
    r'c:\Users\JHJ\Desktop\finetune-platform\server\api\skills.py',
    r'c:\Users\JHJ\Desktop\finetune-platform\server\api\inference\routes.py',
]

for filepath in files_to_check:
    print(f"\n=== Checking {os.path.basename(filepath)} ===")
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        print(f"OK: File size {len(content)} chars")
    except UnicodeDecodeError as e:
        print(f"FAIL: {e}")
        with open(filepath, 'rb') as f:
            data = f.read()
        print(f"  Raw bytes around error: {data[max(0,e.start-10):e.end+10]}")
    except Exception as e:
        print(f"ERROR: {e}")
