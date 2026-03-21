# -*- coding: utf-8 -*-
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("Testing individual imports...")

# Test api.errors
print("\n1. Testing api.errors...")
try:
    from api import errors
    print("   api.errors: OK")
except Exception as e:
    print(f"   api.errors: FAILED - {e}")

# Test api.skills
print("\n2. Testing api.skills...")
try:
    from api import skills
    print("   api.skills: OK")
except Exception as e:
    print(f"   api.skills: FAILED - {e}")

# Test memory.operation_memory
print("\n3. Testing memory.operation_memory...")
try:
    from memory import operation_memory
    print("   memory.operation_memory: OK")
except Exception as e:
    print(f"   memory.operation_memory: FAILED - {e}")

# Test memory.preference_learner
print("\n4. Testing memory.preference_learner...")
try:
    from memory import preference_learner
    print("   memory.preference_learner: OK")
except Exception as e:
    print(f"   memory.preference_learner: FAILED - {e}")

# Test memory
print("\n5. Testing memory...")
try:
    import memory
    print("   memory: OK")
except Exception as e:
    print(f"   memory: FAILED - {e}")

# Test api
print("\n6. Testing api...")
try:
    import api
    print("   api: OK")
except Exception as e:
    print(f"   api: FAILED - {e}")

print("\nDone!")
