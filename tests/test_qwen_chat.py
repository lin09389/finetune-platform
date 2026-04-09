import requests


def main() -> None:
    print("Test Qwen3.5-2B streaming response...\n")

    prompt = "<|im_start|>user\nHello<|im_end|>\n<|im_start|>assistant\n"

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

    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(f"Reply: {result['text']}")
    else:
        print(f"Error: {response.text}")


if __name__ == "__main__":
    main()
