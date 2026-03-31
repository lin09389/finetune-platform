import httpx
import json

url = "http://localhost:8000/training/start"

# 使用 LoRA 方法，不使用量化
data = {
    "model_id": "Qwen3.5-2B",
    "dataset_id": "test_alpaca",
    "method": "lora",  # 使用 LoRA，不是 QLoRA
    "rank": 8,
    "alpha": 16,
    "learning_rate": 5e-5,
    "epochs": 1,
    "batch_size": 1,
    "gradient_accumulation": 16,
    "max_seq_length": 512,
    "warmup_steps": 100,
    "save_steps": 500,
    "logging_steps": 10,
    "quantization": 0  # 不使用量化
}

print("发送 LoRA 训练请求...")
print(f"method: {data['method']}, quantization: {data['quantization']}")

try:
    response = httpx.post(url, json=data, timeout=60)
    print(f"\n状态码: {response.status_code}")
    try:
        resp_json = response.json()
        print(f"响应: {json.dumps(resp_json, indent=2, ensure_ascii=False)}")
    except:
        print(f"响应: {response.text}")
except Exception as e:
    print(f"错误: {e}")