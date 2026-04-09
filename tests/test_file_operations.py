import requests

BASE_URL = "http://127.0.0.1:8001"


def main() -> None:
    print("Test smart-agent file operations")
    print("=" * 60)

    print("\n1. Create file")
    response = requests.post(
        f"{BASE_URL}/smart-agent/smart-execute",
        json={"message": "create file test_smart.txt", "auto_execute": True},
    )
    data = response.json()
    print(f"Detected: {data.get('detected')}")
    print(f"Action: {data.get('action')}")
    print(f"Feedback: {data.get('feedback')}")

    print("\n2. Write file")
    response = requests.post(
        f"{BASE_URL}/smart-agent/smart-execute",
        json={"message": "write Hello World to test_smart.txt", "auto_execute": True},
    )
    data = response.json()
    print(f"Detected: {data.get('detected')}")
    print(f"Action: {data.get('action')}")
    print(f"Feedback: {data.get('feedback')}")

    print("\n3. Read file")
    response = requests.post(
        f"{BASE_URL}/smart-agent/smart-execute",
        json={"message": "read test_smart.txt", "auto_execute": True},
    )
    data = response.json()
    print(f"Detected: {data.get('detected')}")
    print(f"Action: {data.get('action')}")
    print(f"Feedback: {data.get('feedback')}")
    if data.get('result_data'):
        print(f"Result: {data['result_data']}")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
