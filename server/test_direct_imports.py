import sys

sys.path.insert(0, r'c:\Users\JHJ\Desktop\finetune-platform\server')

print("Testing direct imports...")

# Test api.errors
print("\n1. Testing api.errors...")
try:
    print("   OK")
except Exception as e:
    print(f"   FAIL: {e}")

# Test api.ocr
print("\n2. Testing api.ocr...")
try:
    print("   OK")
except Exception as e:
    print(f"   FAIL: {e}")

# Test api.skills
print("\n3. Testing api.skills...")
try:
    print("   OK")
except Exception as e:
    print(f"   FAIL: {e}")

# Test api.inference.routes
print("\n4. Testing api.inference.routes...")
try:
    print("   OK")
except Exception as e:
    print(f"   FAIL: {e}")

print("\nDone!")
