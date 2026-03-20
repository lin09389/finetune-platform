import requests
import json

# Test inference API
url = "http://localhost:8000/inference/stream"
data = {
    "modelId": "Qwen3.5-2B",
    "prompt": "你好",
    "maxTokens": 50
}

print(f"Sending request to {url}")
print(f"Data: {json.dumps(data, ensure_ascii=False)}")

try:
    response = requests.post(
        url,
        json=data,
        headers={"Content-Type": "application/json"},
        stream=True,
        timeout=120
    )
    
    print(f"Status: {response.status_code}")
    print(f"Headers: {dict(response.headers)}")
    
    if response.status_code != 200:
        print(f"Error: {response.text}")
    else:
        for line in response.iter_lines():
            if line:
                print(f"Received: {line.decode('utf-8')}")
except Exception as e:
    print(f"Exception: {e}")