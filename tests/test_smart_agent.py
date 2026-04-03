import requests

BASE_URL = 'http://127.0.0.1:8001'


def main() -> None:
    print('=' * 60)
    print('娴嬭瘯鏅鸿兘 Agent 鑷姩鍒ゆ柇骞舵墽琛屾搷浣?')
    print('=' * 60)

    print('\n1. 娴嬭瘯: 鎴浘')
    response = requests.post(
        f'{BASE_URL}/smart-agent/smart-execute',
        json={'message': '鎴睆', 'auto_execute': True},
    )
    data = response.json()
    print(f"妫€娴嬪埌: {data.get('detected')}")
    print(f"鎿嶄綔: {data.get('action')}")
    print(f"鎵ц鎴愬姛: {data.get('success')}")
    print(f"鍙嶉: {data.get('feedback')}")

    print('\n2. 娴嬭瘯: 鑾峰彇榧犳爣浣嶇疆')
    response = requests.post(
        f'{BASE_URL}/smart-agent/smart-execute',
        json={'message': '榧犳爣鍦ㄥ摢閲?', 'auto_execute': True},
    )
    data = response.json()
    print(f"妫€娴嬪埌: {data.get('detected')}")
    print(f"鎿嶄綔: {data.get('action')}")
    print(f"鎵ц鎴愬姛: {data.get('success')}")
    print(f"鍙嶉: {data.get('feedback')}")

    print('\n3. 娴嬭瘯: 鍒楀嚭绐楀彛')
    response = requests.post(
        f'{BASE_URL}/smart-agent/smart-execute',
        json={'message': '鍒楀嚭鎵€鏈夌獥鍙?', 'auto_execute': True},
    )
    data = response.json()
    print(f"妫€娴嬪埌: {data.get('detected')}")
    print(f"鎿嶄綔: {data.get('action')}")
    print(f"鎵ц鎴愬姛: {data.get('success')}")
    print(f"鍙嶉: {data.get('feedback')}")
    if data.get('result_data'):
        print(f"绐楀彛鏁伴噺: {data['result_data'].get('count')}")

    print('\n' + '=' * 60)
    print('娴嬭瘯瀹屾垚!')
    print('=' * 60)


if __name__ == '__main__':
    main()
