import requests


def main() -> None:
    print("娴嬭瘯 Ollama qwen3:4b 妯″瀷杈撳嚭璐ㄩ噺...\n")

    print("1. 绠€鍗曢棶鍊欐祴璇?")
    response = requests.post(
        "http://127.0.0.1:8000/inference/generate",
        json={"model_id": "qwen3:4b", "prompt": "浣犲ソ", "max_tokens": 100, "backend": "ollama"},
        timeout=60,
    )
    result = response.json()
    print("杈撳叆: 浣犲ソ")
    print(f"杈撳嚭: {result['text'][:200]}...")
    print()

    print("2. 鏁板闂娴嬭瘯:")
    response = requests.post(
        "http://127.0.0.1:8000/inference/generate",
        json={"model_id": "qwen3:4b", "prompt": "1+1绛変簬鍑狅紵", "max_tokens": 100, "backend": "ollama"},
        timeout=60,
    )
    result = response.json()
    print("杈撳叆: 1+1绛変簬鍑狅紵")
    print(f"杈撳嚭: {result['text'][:200]}...")
    print()

    print("3. 浠ｇ爜闂娴嬭瘯:")
    response = requests.post(
        "http://127.0.0.1:8000/inference/generate",
        json={
            "model_id": "qwen3:4b",
            "prompt": "鍐欎竴涓?Python 鍑芥暟璁＄畻鏂愭尝閭ｅ鏁板垪",
            "max_tokens": 200,
            "backend": "ollama",
        },
        timeout=60,
    )
    result = response.json()
    print("杈撳叆: 鍐欎竴涓?Python 鍑芥暟璁＄畻鏂愭尝閭ｅ鏁板垪")
    print(f"杈撳嚭: {result['text'][:300]}...")
    print()

    print("4. 娴嬭瘯 gemma3:4b:")
    response = requests.post(
        "http://127.0.0.1:8000/inference/generate",
        json={"model_id": "gemma3:4b", "prompt": "浣犲ソ", "max_tokens": 100, "backend": "ollama"},
        timeout=60,
    )
    result = response.json()
    print("杈撳叆: 浣犲ソ")
    print(f"杈撳嚭: {result['text'][:200]}...")


if __name__ == "__main__":
    main()
