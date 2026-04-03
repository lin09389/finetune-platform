import json
import requests

BASE_URL = 'http://127.0.0.1:8000'


def main() -> None:
    print('=' * 50)
    print('娴嬭瘯 Agent API')
    print('=' * 50)

    print('\n[娴嬭瘯 1] 妫€娴嬫剰鍥? 鎵撳紑璁＄畻鍣?')
    response = requests.post(
        f'{BASE_URL}/agent/detect-intent',
        json={'message': '鎵撳紑璁＄畻鍣?'},
    )
    print(f'鐘舵€佺爜: {response.status_code}')
    print(f"鍝嶅簲: {json.dumps(response.json(), ensure_ascii=False, indent=2)}")

    print('\n[娴嬭瘯 2] 鎵ц鎿嶄綔: app_open calculator')
    response = requests.post(
        f'{BASE_URL}/agent/execute',
        json={'action': 'app_open', 'params': {'app_name': 'calculator'}},
    )
    print(f'鐘舵€佺爜: {response.status_code}')
    print(f"鍝嶅簲: {json.dumps(response.json(), ensure_ascii=False, indent=2)}")

    print('\n[娴嬭瘯 3] chat-execute: 鎵撳紑璁＄畻鍣?')
    response = requests.post(
        f'{BASE_URL}/agent/chat-execute',
        json={'message': '鎵撳紑璁＄畻鍣?', 'auto_confirm': False},
    )
    print(f'鐘舵€佺爜: {response.status_code}')
    print(f"鍝嶅簲: {json.dumps(response.json(), ensure_ascii=False, indent=2)}")

    print('\n[娴嬭瘯 4] 鎵ц鎿嶄綔: app_open notepad')
    response = requests.post(
        f'{BASE_URL}/agent/execute',
        json={'action': 'app_open', 'params': {'app_name': 'notepad'}},
    )
    print(f'鐘舵€佺爜: {response.status_code}')
    print(f"鍝嶅簲: {json.dumps(response.json(), ensure_ascii=False, indent=2)}")

    print('\n' + '=' * 50)
    print('娴嬭瘯瀹屾垚')
    print('=' * 50)


if __name__ == '__main__':
    main()
