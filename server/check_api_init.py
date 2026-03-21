# -*- coding: utf-8 -*-
import os

filepath = r'c:\Users\JHJ\Desktop\finetune-platform\server\api\__init__.py'

with open(filepath, 'rb') as f:
    data = f.read()

print(f'File size: {len(data)} bytes')
print(f'First 20 bytes (hex): {data[:20].hex()}')
print(f'First 20 bytes (repr): {repr(data[:20])}')

# Check for BOM
if data.startswith(b'\xef\xbb\xbf'):
    print('Has UTF-8 BOM')
elif data.startswith(b'\xff\xfe'):
    print('Has UTF-16 LE BOM')
elif data.startswith(b'\xfe\xff'):
    print('Has UTF-16 BE BOM')
else:
    print('No BOM detected')

# Try to decode
try:
    text = data.decode('utf-8')
    print(f'UTF-8 decode: OK ({len(text)} chars)')
    print(f'First line: {text.split(chr(10))[0]}')
except UnicodeDecodeError as e:
    print(f'UTF-8 decode FAIL: {e}')
