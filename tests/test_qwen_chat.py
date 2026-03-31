import requests
import json

# 测试使用正确的 chat template
print("测试 Qwen3.5-2B 模型推理...\n")

# Qwen3.5 的正确提示格式
prompt = "<|im_start|>user\n你好<|im_end|>\n<|im_start|>assistant\n"

response = requests.post(
    "http://127.0.0.1:8000/inference/generate",
    json={
        "model_id": "Qwen3.5-2B",
        "prompt": prompt,
        "max_tokens": 100,
        "temperature": 0.7
    },
    timeout=120
)

print(f"状态码: {response.status_code}")
if response.status_code == 200:
    result = response.json()
    print(f"输出: {result['text']}")
else:
    print(f"错误: {response.text}")