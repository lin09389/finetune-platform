import requests


def main() -> None:
    print("Test Ollama qwen3:4b model quality...\n")

    print("1. Basic greeting")
    response = requests.post(
        "http://127.0.0.1:8000/inference/generate",
        json={"model_id": "qwen3:4b", "prompt": "Hello", "max_tokens": 100, "backend": "ollama"},
        timeout=60,
    )
    result = response.json()
    print("Prompt: Hello")
    print(f"Reply: {result['text'][:200]}...")
    print()

    print("2. Simple math")
    response = requests.post(
        "http://127.0.0.1:8000/inference/generate",
        json={"model_id": "qwen3:4b", "prompt": "What is 1+1?", "max_tokens": 100, "backend": "ollama"},
        timeout=60,
    )
    result = response.json()
    print("Prompt: What is 1+1?")
    print(f"Reply: {result['text'][:200]}...")
    print()

    print("3. Python code generation")
    response = requests.post(
        "http://127.0.0.1:8000/inference/generate",
        json={
            "model_id": "qwen3:4b",
            "prompt": "Write a short Python hello world example.",
            "max_tokens": 200,
            "backend": "ollama",
        },
        timeout=60,
    )
    result = response.json()
    print("Prompt: Write a short Python hello world example.")
    print(f"Reply: {result['text'][:300]}...")
    print()

    print("4. Test gemma3:4b")
    response = requests.post(
        "http://127.0.0.1:8000/inference/generate",
        json={"model_id": "gemma3:4b", "prompt": "Hello", "max_tokens": 100, "backend": "ollama"},
        timeout=60,
    )
    result = response.json()
    print("Prompt: Hello")
    print(f"Reply: {result['text'][:200]}...")


if __name__ == "__main__":
    main()
