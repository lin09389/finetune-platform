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

        print(f'{os.path.basename(filepath)}:')
        print(f'  Size: {size} bytes')
        print(f'  Last 50 bytes: {data[-50:]}')

        # Check if file ends with newline
        if data.endswith(b'\n'):
            print('  Ends with newline: YES')
        elif data.endswith(b'\r\n'):
            print('  Ends with CRLF: YES')
        else:
            print('  Ends with newline: NO')

        # Try to decode entire file
        try:
            text = data.decode('utf-8')
            print(f'  UTF-8 decode: OK ({len(text)} chars)')
        except UnicodeDecodeError as e:
            print(f'  UTF-8 decode FAIL: {e}')

        print()
