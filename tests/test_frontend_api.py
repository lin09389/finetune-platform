import json
import requests


def main() -> None:
    print("Test frontend inference APIs...")

    print("\n1. List backends")
    response = requests.get("http://127.0.0.1:8000/inference/backends")
    print(json.dumps(response.json(), ensure_ascii=False, indent=2))

    print("\n2. List Hugging Face models")
    response = requests.get("http://127.0.0.1:8000/inference/models")
    print(json.dumps(response.json(), ensure_ascii=False, indent=2))

    print("\n3. Get Ollama status")
    response = requests.get("http://127.0.0.1:8000/inference/ollama/status")
    print(json.dumps(response.json(), ensure_ascii=False, indent=2))

    print("\n4. Test Hugging Face stream")
    try:
        response = requests.post(
            "http://127.0.0.1:8000/inference/stream",
            json={"model_id": "Qwen3.5-2B", "prompt": "Hello", "max_tokens": 30},
            stream=True,
            timeout=120,
        )
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            for line in response.iter_lines():
                if not line:
                    continue
                decoded = line.decode("utf-8")
                if decoded.startswith("data: "):
                    data = decoded[6:]
                    if data != "[DONE]":
                        try:
                            parsed = json.loads(data)
                            if "content" in parsed:
                                print(parsed["content"], end="", flush=True)
                        except Exception:
                            pass
            print()
        else:
            print(response.text)
    except Exception as error:
        print(error)

    print("\n5. Test Ollama stream")
    try:
        response = requests.post(
            "http://127.0.0.1:8000/inference/stream",
            json={"model_id": "qwen3:4b", "prompt": "Hello", "max_tokens": 30, "backend": "ollama"},
            stream=True,
            timeout=120,
        )
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            for line in response.iter_lines():
                if not line:
                    continue
                decoded = line.decode("utf-8")
                if decoded.startswith("data: "):
                    data = decoded[6:]
                    if data != "[DONE]":
                        try:
                            parsed = json.loads(data)
                            if "content" in parsed:
                                print(parsed["content"], end="", flush=True)
                        except Exception:
                            pass
            print()
        else:
            print(response.text)
    except Exception as error:
        print(error)


if __name__ == "__main__":
    main()
