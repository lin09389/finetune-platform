
filepath = r'c:\Users\JHJ\Desktop\finetune-platform\server\api\__init__.py'

with open(filepath, 'rb') as f:
    data = f.read()

print(f'File size: {len(data)} bytes')
print(f'First 20 bytes (hex): {data[:20].hex()}')
print(f'First 20 bytes (repr): {repr(data[:20])}')

# Check bytes 6-7
print(f'\nBytes 6-7: {data[6:8]}')
print(f'Hex: {data[6:8].hex()}')

# Try decode
try:
    text = data.decode('utf-8')
    print(f'\nUTF-8 decode OK: {len(text)} chars')
    print(f'First line: {text.split(chr(10))[0]}')
except UnicodeDecodeError as e:
    print(f'\nUTF-8 decode FAIL: {e}')
