import requests
import json

# 测试 Ollama 模型输出
print("测试 Ollama qwen3:4b 模型输出质量...\n")

# 1. 简单问候
print("1. 简单问候测试:")
response = requests.post(
    "http://127.0.0.1:8000/inference/generate",
    json={
        "model_id": "qwen3:4b",
        "prompt": "你好",
        "max_tokens": 100,
        "backend": "ollama"
    },
    timeout=60
)
result = response.json()
print(f"输入: 你好")
print(f"输出: {result['text'][:200]}...")
print()

# 2. 数学问题
print("2. 数学问题测试:")
response = requests.post(
    "http://127.0.0.1:8000/inference/generate",
    json={
        "model_id": "qwen3:4b",
        "prompt": "1+1等于几？",
        "max_tokens": 100,
        "backend": "ollama"
    },
    timeout=60
)
result = response.json()
print(f"输入: 1+1等于几？")
print(f"输出: {result['text'][:200]}...")
print()

# 3. 代码问题
print("3. 代码问题测试:")
response = requests.post(
    "http://127.0.0.1:8000/inference/generate",
    json={
        "model_id": "qwen3:4b",
        "prompt": "写一个 Python 函数计算斐波那契数列",
        "max_tokens": 200,
        "backend": "ollama"
    },
    timeout=60
)
result = response.json()
print(f"输入: 写一个 Python 函数计算斐波那契数列")
print(f"输出: {result['text'][:300]}...")
print()

# 4. 测试 gemma3:4b
print("4. 测试 gemma3:4b:")
response = requests.post(
    "http://127.0.0.1:8000/inference/generate",
    json={
        "model_id": "gemma3:4b",
        "prompt": "你好",
        "max_tokens": 100,
        "backend": "ollama"
    },
    timeout=60
)
result = response.json()
print(f"输入: 你好")
print(f"输出: {result['text'][:200]}...")