import requests


def main() -> None:
    print("娴嬭瘯 Qwen3.5-2B 妯″瀷鎺ㄧ悊...\n")

    prompt = "<|im_start|>user\n浣犲ソ<|im_end|>\n<|im_start|>assistant\n"

    response = requests.post(
        "http://127.0.0.1:8000/inference/generate",
        json={
            "model_id": "Qwen3.5-2B",
            "prompt": prompt,
            "max_tokens": 100,
            "temperature": 0.7,
        },
        timeout=120,
    )

    print(f"鐘舵€佺爜: {response.status_code}")
    if response.status_code == 200:
      result = response.json()
      print(f"杈撳嚭: {result['text']}")
    else:
      print(f"閿欒: {response.text}")


if __name__ == "__main__":
    main()
