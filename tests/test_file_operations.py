import requests

BASE_URL = 'http://127.0.0.1:8001'


def main() -> None:
    print('娴嬭瘯鏅鸿兘 Agent 鏂囦欢鎿嶄綔')
    print('=' * 60)

    print('\n1. 娴嬭瘯: 鍒涘缓鏂囦欢')
    response = requests.post(
        f'{BASE_URL}/smart-agent/smart-execute',
        json={'message': '鍒涘缓 test_smart.txt 鏂囦欢', 'auto_execute': True},
    )
    data = response.json()
    print(f"妫€娴嬪埌: {data.get('detected')}")
    print(f"鎿嶄綔: {data.get('action')}")
    print(f"鍙嶉: {data.get('feedback')}")

    print('\n2. 娴嬭瘯: 鍐欏叆鏂囦欢')
    response = requests.post(
        f'{BASE_URL}/smart-agent/smart-execute',
        json={'message': '鎶?test_smart.txt 鐨勫唴瀹规敼鎴?Hello World', 'auto_execute': True},
    )
    data = response.json()
    print(f"妫€娴嬪埌: {data.get('detected')}")
    print(f"鎿嶄綔: {data.get('action')}")
    print(f"鍙嶉: {data.get('feedback')}")

    print('\n3. 娴嬭瘯: 璇诲彇鏂囦欢')
    response = requests.post(
        f'{BASE_URL}/smart-agent/smart-execute',
        json={'message': '璇诲彇 test_smart.txt', 'auto_execute': True},
    )
    data = response.json()
    print(f"妫€娴嬪埌: {data.get('detected')}")
    print(f"鎿嶄綔: {data.get('action')}")
    print(f"鍙嶉: {data.get('feedback')}")
    if data.get('result_data'):
      print(f"缁撴灉: {data['result_data']}")

    print('\n' + '=' * 60)


if __name__ == '__main__':
    main()
