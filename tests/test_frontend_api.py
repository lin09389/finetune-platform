import json
import requests


def main() -> None:
    print('娴嬭瘯鍓嶇 API 璋冪敤...')

    print('\n1. 鑾峰彇鍚庣鍒楄〃:')
    response = requests.get('http://127.0.0.1:8000/inference/backends')
    print(json.dumps(response.json(), ensure_ascii=False, indent=2))

    print('\n2. 鑾峰彇 HuggingFace 妯″瀷鍒楄〃:')
    response = requests.get('http://127.0.0.1:8000/inference/models')
    print(json.dumps(response.json(), ensure_ascii=False, indent=2))

    print('\n3. 鑾峰彇 Ollama 鐘舵€?')
    response = requests.get('http://127.0.0.1:8000/inference/ollama/status')
    print(json.dumps(response.json(), ensure_ascii=False, indent=2))

    print('\n4. 娴嬭瘯 HuggingFace 娴佸紡鎺ㄧ悊:')
    try:
        response = requests.post(
            'http://127.0.0.1:8000/inference/stream',
            json={'model_id': 'Qwen3.5-2B', 'prompt': '浣犲ソ', 'max_tokens': 30},
            stream=True,
            timeout=120,
        )
        print(f'鐘舵€佺爜: {response.status_code}')
        if response.status_code == 200:
            for line in response.iter_lines():
                if line:
                    decoded = line.decode('utf-8')
                    if decoded.startswith('data: '):
                        data = decoded[6:]
                        if data != '[DONE]':
                            try:
                                parsed = json.loads(data)
                                if 'content' in parsed:
                                    print(parsed['content'], end='', flush=True)
                            except Exception:
                                pass
            print()
        else:
            print(f'閿欒: {response.text}')
    except Exception as error:
        print(f'閿欒: {error}')

    print('\n5. 娴嬭瘯 Ollama 娴佸紡鎺ㄧ悊:')
    try:
        response = requests.post(
            'http://127.0.0.1:8000/inference/stream',
            json={'model_id': 'qwen3:4b', 'prompt': '浣犲ソ', 'max_tokens': 30, 'backend': 'ollama'},
            stream=True,
            timeout=120,
        )
        print(f'鐘舵€佺爜: {response.status_code}')
        if response.status_code == 200:
            for line in response.iter_lines():
                if line:
                    decoded = line.decode('utf-8')
                    if decoded.startswith('data: '):
                        data = decoded[6:]
                        if data != '[DONE]':
                            try:
                                parsed = json.loads(data)
                                if 'content' in parsed:
                                    print(parsed['content'], end='', flush=True)
                            except Exception:
                                pass
            print()
        else:
            print(f'閿欒: {response.text}')
    except Exception as error:
        print(f'閿欒: {error}')


if __name__ == '__main__':
    main()
