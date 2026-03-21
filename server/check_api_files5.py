# -*- coding: utf-8 -*-
import os

# Check if files exist
files = [
    r'c:\Users\JHJ\Desktop\finetune-platform\server\api\errors.py',
    r'c:\Users\JHJ\Desktop\finetune-platform\server\api\ocr.py',
    r'c:\Users\JHJ\Desktop\finetune-platform\server\api\skills.py',
]

for f in files:
    exists = os.path.exists(f)
    print(f'{os.path.basename(f)}: exists={exists}')
    if exists:
        # Try to import
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("test_module", f)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            print(f'  Import: OK')
        except Exception as e:
            print(f'  Import FAIL: {e}')
