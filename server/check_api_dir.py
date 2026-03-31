import os

api_dir = r'c:\Users\JHJ\Desktop\finetune-platform\server\api'

# List all .py files
for f in os.listdir(api_dir):
    if f.endswith('.py'):
        filepath = os.path.join(api_dir, f)
        with open(filepath, 'rb') as file:
            data = file.read()

        print(f'{f}:')
        print(f'  Size: {len(data)} bytes')
        print(f'  First 20 bytes (hex): {data[:20].hex()}')
        print(f'  First 20 bytes (repr): {repr(data[:20])}')

        # Check bytes 6-7
        if len(data) >= 8:
            print(f'  Bytes 6-7: {data[6:8].hex()} = {repr(data[6:8])}')

        print()
