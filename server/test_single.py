# -*- coding: utf-8 -*-
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("Testing skills import...")
try:
    import skills
    print("skills imported successfully!")
except Exception as e:
    print(f"Failed to import skills: {e}")
    import traceback
    traceback.print_exc()
