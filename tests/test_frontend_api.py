import requests
import json

# 测试前端调用的 API
print("测试前端 API 调用...")

# 1. 获取后端列表
print("\n1. 获取后端列表:")
response = requests.get("http://127.0.0.1:8000/inference/backends")
print(json.dumps(response.json(), ensure_ascii=False, indent=2))

# 2. 获取模型列表
print("\n2. 获取 HuggingFace 模型列表:")
response = requests.get("http://127.0.0.1:8000/inference/models")
print(json.dumps(response.json(), ensure_ascii=False, indent=2))

# 3. 获取 Ollama 状态
print("\n3. 获取 Ollama 状态:")
response = requests.get("http://127.0.0.1:8000/inference/ollama/status")
print(json.dumps(response.json(), ensure_ascii=False, indent=2))

# 4. 测试流式推理 (HuggingFace)
print("\n4. 测试 HuggingFace 流式推理:")
try:
    response = requests.post(
        "http://127.0.0.1:8000/inference/stream",
        json={
            "model_id": "Qwen3.5-2B",
            "prompt": "你好",
            "max_tokens": 30
        },
        stream=True,
        timeout=120
    )
    print(f"状态码: {response.status_code}")
    if response.status_code == 200:
        for line in response.iter_lines():
            if line:
                decoded = line.decode('utf-8')
                if decoded.startswith('data: '):
                    data = decoded[6:]
                    if data != '[DONE]':
                        try:
                            parsed = json.loads(data)
                            if 'content' in parsed:
                                print(parsed['content'], end='', flush=True)
                        except:
                            pass
        print()
    else:
        print(f"错误: {response.text}")
except Exception as e:
    print(f"错误: {e}")

# 5. 测试流式推理 (Ollama)
print("\n5. 测试 Ollama 流式推理:")
try:
    response = requests.post(
        "http://127.0.0.1:8000/inference/stream",
        json={
            "model_id": "qwen3:4b",
            "prompt": "你好",
            "max_tokens": 30,
            "backend": "ollama"
        },
        stream=True,
        timeout=120
    )
    print(f"状态码: {response.status_code}")
    if response.status_code == 200:
        for line in response.iter_lines():
            if line:
                decoded = line.decode('utf-8')
                if decoded.startswith('data: '):
                    data = decoded[6:]
                    if data != '[DONE]':
                        try:
                            parsed = json.loads(data)
                            if 'content' in parsed:
                                print(parsed['content'], end='', flush=True)
                        except:
                            pass
        print()
    else:
        print(f"错误: {response.text}")
except Exception as e:
    print(f"错误: {e}")