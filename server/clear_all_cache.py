# -*- coding: utf-8 -*-
import os
import shutil
import sys

server_dir = r'c:\Users\JHJ\Desktop\finetune-platform\server'

# Clear all __pycache__ directories
count = 0
for root, dirs, files in os.walk(server_dir):
    if '__pycache__' in dirs:
        pycache_path = os.path.join(root, '__pycache__')
        try:
            shutil.rmtree(pycache_path)
            count += 1
            print(f"Removed: {pycache_path}")
        except Exception as e:
            print(f"Failed to remove {pycache_path}: {e}")

print(f"\nRemoved {count} __pycache__ directories")

# Clear .pyc files
pyc_count = 0
for root, dirs, files in os.walk(server_dir):
    for f in files:
        if f.endswith('.pyc'):
            pyc_path = os.path.join(root, f)
            try:
                os.remove(pyc_path)
                pyc_count += 1
            except Exception as e:
                print(f"Failed to remove {pyc_path}: {e}")

print(f"Removed {pyc_count} .pyc files")
