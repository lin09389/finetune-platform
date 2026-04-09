import requests

BASE_URL = "http://127.0.0.1:8001"


def main() -> None:
    print("=" * 60)
    print("Test smart-agent behavior routing")
    print("=" * 60)

    print("\n1. Greeting request")
    response = requests.post(
        f"{BASE_URL}/smart-agent/smart-execute",
        json={"message": "hello", "auto_execute": True},
    )
    data = response.json()
    print(f"Detected: {data.get('detected')}")
    print(f"Action: {data.get('action')}")
    print(f"Success: {data.get('success')}")
    print(f"Feedback: {data.get('feedback')}")

    print("\n2. Intent classification request")
    response = requests.post(
        f"{BASE_URL}/smart-agent/smart-execute",
        json={"message": "analyze this intent", "auto_execute": True},
    )
    data = response.json()
    print(f"Detected: {data.get('detected')}")
    print(f"Action: {data.get('action')}")
    print(f"Success: {data.get('success')}")
    print(f"Feedback: {data.get('feedback')}")

    print("\n3. Batch task request")
    response = requests.post(
        f"{BASE_URL}/smart-agent/smart-execute",
        json={"message": "list the current tasks", "auto_execute": True},
    )
    data = response.json()
    print(f"Detected: {data.get('detected')}")
    print(f"Action: {data.get('action')}")
    print(f"Success: {data.get('success')}")
    print(f"Feedback: {data.get('feedback')}")
    if data.get('result_data'):
        print(f"Count: {data['result_data'].get('count')}")

    print("\n" + "=" * 60)
    print("Done")
    print("=" * 60)


if __name__ == "__main__":
    main()
