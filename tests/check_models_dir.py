import os

# Check server/models
server_models = "C:/Users/JHJ/Desktop/finetune-platform/server/models"
if os.path.exists(server_models):
    print(f"server/models exists: {os.listdir(server_models)}")
    for item in os.listdir(server_models):
        full = os.path.join(server_models, item)
        if os.path.isdir(full):
            print(f"\n[{item}]")
            files = os.listdir(full)[:10]  # First 10 files
            for f in files:
                print(f"  {f}")
else:
    print("server/models does NOT exist")

# Check MODELS_DIR in inference.py
print("\n--- Checking config ---")
import sys
sys.path.insert(0, "C:/Users/JHJ/Desktop/finetune-platform/server")
from core.config import get_settings
settings = get_settings()
print(f"models_dir_resolved: {settings.models_dir_resolved}")
print(f"Exists: {settings.models_dir_resolved.exists()}")