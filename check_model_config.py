import json
from pathlib import Path

model_path = Path("C:/Users/JHJ/Desktop/finetune-platform/server/models/Qwen3.5-2B")

# 读取 config.json
config_path = model_path / "config.json"
if config_path.exists():
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    print("模型配置:")
    print(json.dumps(config, indent=2, ensure_ascii=False))
else:
    print("config.json 不存在")

# 读取 model_info.json
info_path = model_path / "model_info.json"
if info_path.exists():
    with open(info_path, "r", encoding="utf-8") as f:
        info = json.load(f)
    print("\n模型信息:")
    print(json.dumps(info, indent=2, ensure_ascii=False))