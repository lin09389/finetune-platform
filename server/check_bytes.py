import os

files = [
    (r'c:\Users\JHJ\Desktop\finetune-platform\server\api\errors.py', 'api.errors'),
    (r'c:\Users\JHJ\Desktop\finetune-platform\server\api\ocr.py', 'api.ocr'),
    (r'c:\Users\JHJ\Desktop\finetune-platform\server\api\skills.py', 'api.skills'),
]

for filepath, modname in files:
    print(f'\n=== {modname} ===')

    if not os.path.exists(filepath):
        print('  File not found!')
        continue

    size = os.path.getsize(filepath)
    print(f'  Size: {size} bytes')

    with open(filepath, 'rb') as f:
        data = f.read()

    print(f'  First 10 bytes: {data[:10]}')
    print(f'  Bytes 5-8: {data[5:8]}')

    # Check bytes 6-7
    if len(data) >= 8:
        b6 = data[6]
        b7 = data[7]
        print(f'  Byte 6: {b6} ({chr(b6) if 32 <= b6 < 127 else "?"})')
        print(f'  Byte 7: {b7} ({chr(b7) if 32 <= b7 < 127 else "?"})')

    # Check if file is complete
    print(f'  Last 10 bytes: {data[-10:]}')

    # Count lines
    lines = data.split(b'\n')
    print(f'  Line count: {len(lines)}')
    print(f'  First line: {lines[0]}')
