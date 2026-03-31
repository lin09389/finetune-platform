"""
意图检测模块测试
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agent.intent import IntentDetector


def test_basic_detection():
    detector = IntentDetector()

    test_cases = [
        "创建一个test.py文件",
        "读取config.json",
        "删除test.py",
        "打开VS Code",
        "截图",
        "列出当前目录",
        "点击坐标 100,200",
        "输入 Hello World",
    ]

    print("=" * 60)
    print("  意图检测测试")
    print("=" * 60)

    for text in test_cases:
        result = detector.detect(text, session_id="test_session")

        status = "✓" if result.detected else "✗"
        method = result.method.value if result.method else "unknown"

        print(f"\n{status} 输入: {text}")
        print(f"   意图: {result.intent_type}")
        print(f"   置信度: {result.confidence:.2f} ({result.confidence_level.value})")
        print(f"   方法: {method}")
        if result.params:
            print(f"   参数: {result.params}")

    print("\n" + "=" * 60)
    print("  性能指标")
    print("=" * 60)
    metrics = detector.get_metrics()
    print(f"总请求数: {metrics.get('total_requests', 0)}")
    print(f"成功率: {metrics.get('success_rate', 0):.2%}")
    print(f"平均响应时间: {metrics.get('average_response_time_ms', 0):.2f}ms")


if __name__ == "__main__":
    test_basic_detection()
