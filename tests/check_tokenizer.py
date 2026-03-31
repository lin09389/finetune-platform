import json
from pathlib import Path

model_path = Path("C:/Users/JHJ/Desktop/finetune-platform/server/models/Qwen3.5-2B")

# 读取 tokenizer_config.json
tokenizer_config_path = model_path / "tokenizer_config.json"
if tokenizer_config_path.exists():
    with open(tokenizer_config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    print("Tokenizer 配置:")
    print(json.dumps(config, indent=2, ensure_ascii=False)[:3000])
else:
    print("tokenizer_config.json 不存在")

# 读取 chat_template.jinja
chat_template_path = model_path / "chat_template.jinja"
if chat_template_path.exists():
    with open(chat_template_path, "r", encoding="utf-8") as f:
        template = f.read()
    print("\n\nChat Template (前500字符):")
    print(template[:500])
else:
    print("chat_template.jinja 不存在")