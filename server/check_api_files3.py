import os

files = [
    r'c:\Users\JHJ\Desktop\finetune-platform\server\api\errors.py',
    r'c:\Users\JHJ\Desktop\finetune-platform\server\api\ocr.py',
    r'c:\Users\JHJ\Desktop\finetune-platform\server\api\skills.py',
    r'c:\Users\JHJ\Desktop\finetune-platform\server\api\inference\routes.py',
]

for filepath in files:
    if os.path.exists(filepath):
        with open(filepath, 'rb') as f:
            data = f.read()

        print(f'{os.path.basename(filepath)}:')
        print(f'  Size: {len(data)} bytes')
        print(f'  First 50 bytes: {data[:50]}')

        # Check if it starts with valid UTF-8 BOM or coding declaration
        if data.startswith(b'\xef\xbb\xbf'):
            print('  Has UTF-8 BOM')
        elif data.startswith(b'# -*- coding:'):
            print('  Has coding declaration')
        else:
            print('  No coding declaration found')

        # Try to decode first line
        try:
            first_line = data.split(b'\n')[0]
            print(f'  First line: {first_line}')
        except Exception as e:
            print(f'  Error getting first line: {e}')

        print()
