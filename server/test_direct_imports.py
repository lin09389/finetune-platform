# -*- coding: utf-8 -*-
import sys
import os
sys.path.insert(0, r'c:\Users\JHJ\Desktop\finetune-platform\server')

print("Testing direct imports...")

# Test api.errors
print("\n1. Testing api.errors...")
try:
    import api.errors
    print("   OK")
except Exception as e:
    print(f"   FAIL: {e}")

# Test api.ocr
print("\n2. Testing api.ocr...")
try:
    import api.ocr
    print("   OK")
except Exception as e:
    print(f"   FAIL: {e}")

# Test api.skills
print("\n3. Testing api.skills...")
try:
    import api.skills
    print("   OK")
except Exception as e:
    print(f"   FAIL: {e}")

# Test api.inference.routes
print("\n4. Testing api.inference.routes...")
try:
    import api.inference.routes
    print("   OK")
except Exception as e:
    print(f"   FAIL: {e}")

print("\nDone!")
