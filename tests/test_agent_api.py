import json
import requests

BASE_URL = "http://127.0.0.1:8000"
SAMPLE_MESSAGE = "Please open calculator"


def main() -> None:
    print("=" * 50)
    print("Test Agent API")
    print("=" * 50)

    print("\n[Test 1] Detect intent")
    response = requests.post(
        f"{BASE_URL}/agent/detect-intent",
        json={"message": SAMPLE_MESSAGE},
    )
    print(f"Status: {response.status_code}")
    print(json.dumps(response.json(), ensure_ascii=False, indent=2))

    print("\n[Test 2] Execute action: app_open calculator")
    response = requests.post(
        f"{BASE_URL}/agent/execute",
        json={"action": "app_open", "params": {"app_name": "calculator"}},
    )
    print(f"Status: {response.status_code}")
    print(json.dumps(response.json(), ensure_ascii=False, indent=2))

    print("\n[Test 3] Chat execute")
    response = requests.post(
        f"{BASE_URL}/agent/chat-execute",
        json={"message": SAMPLE_MESSAGE, "auto_confirm": False},
    )
    print(f"Status: {response.status_code}")
    print(json.dumps(response.json(), ensure_ascii=False, indent=2))

    print("\n[Test 4] Execute action: app_open notepad")
    response = requests.post(
        f"{BASE_URL}/agent/execute",
        json={"action": "app_open", "params": {"app_name": "notepad"}},
    )
    print(f"Status: {response.status_code}")
    print(json.dumps(response.json(), ensure_ascii=False, indent=2))

    print("\n" + "=" * 50)
    print("Done")
    print("=" * 50)


if __name__ == "__main__":
    main()
