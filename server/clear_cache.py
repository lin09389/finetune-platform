import os
import shutil

server_dir = r'c:\Users\JHJ\Desktop\finetune-platform\server'

# Clear all __pycache__ directories
for root, dirs, files in os.walk(server_dir):
    if '__pycache__' in dirs:
        pycache_path = os.path.join(root, '__pycache__')
        print(f"Removing: {pycache_path}")
        try:
            shutil.rmtree(pycache_path)
        except Exception as e:
            print(f"  Failed: {e}")

# Clear .pyc files
for root, dirs, files in os.walk(server_dir):
    for f in files:
        if f.endswith('.pyc'):
            pyc_path = os.path.join(root, f)
            print(f"Removing: {pyc_path}")
            try:
                os.remove(pyc_path)
            except Exception as e:
                print(f"  Failed: {e}")

print("\nCache cleared!")
