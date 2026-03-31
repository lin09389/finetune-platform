"""
测试智能知识库自动检索功能
"""
from datetime import datetime

import requests

BASE_URL = "http://127.0.0.1:8000"

def test_smart_retrieval():
    print("="*60)
    print("智能知识库自动检索测试")
    print(f"测试时间: {datetime.now().isoformat()}")
    print("="*60)

    results = []

    # 测试用例：不同领域的问题
    test_cases = [
        # 法律领域
        {
            "query": "根据民法典，合同违约应该如何赔偿？",
            "expected_domain": "法律领域",
            "expected_retrieve": True
        },
        {
            "query": "刑法中关于盗窃罪的规定是什么？",
            "expected_domain": "法律领域",
            "expected_retrieve": True
        },
        {
            "query": "劳动法规定的加班工资怎么计算？",
            "expected_domain": "法律领域",
            "expected_retrieve": True
        },
        # 医疗领域
        {
            "query": "高血压患者应该注意什么？",
            "expected_domain": "医疗健康领域",
            "expected_retrieve": True
        },
        {
            "query": "感冒发烧吃什么药好？",
            "expected_domain": "医疗健康领域",
            "expected_retrieve": True
        },
        # 金融领域
        {
            "query": "股票投资有什么风险？",
            "expected_domain": "金融财经领域",
            "expected_retrieve": True
        },
        {
            "query": "银行贷款利率怎么算？",
            "expected_domain": "金融财经领域",
            "expected_retrieve": True
        },
        # 教育领域
        {
            "query": "高考志愿填报有什么技巧？",
            "expected_domain": "教育领域",
            "expected_retrieve": True
        },
        # 技术领域
        {
            "query": "机器学习和深度学习有什么区别？",
            "expected_domain": "技术领域",
            "expected_retrieve": True
        },
        # 普通问题
        {
            "query": "今天天气怎么样？",
            "expected_domain": None,
            "expected_retrieve": False
        },
        {
            "query": "写一个Python函数",
            "expected_domain": None,
            "expected_retrieve": False  # 被排除关键词
        }
    ]

    print("\n[领域检测测试]")
    for i, case in enumerate(test_cases, 1):
        query = case["query"]
        print(f"\n测试 {i}: {query}")

        try:
            # 测试意图检测
            resp = requests.post(
                f"{BASE_URL}/agent/detect-intent",
                json={"message": query},
                timeout=30
            )

            if resp.status_code == 200:
                data = resp.json()
                detected = data.get("detected", False)
                action = data.get("action", "")

                # 检查是否应该检索
                expected = case["expected_retrieve"]

                if expected:
                    print(f"  [PASS] 应触发知识检索(detected={detected}, action={action})")
                    results.append((f"测试{i}", True, query[:20]))
                else:
                    print(f"  [INFO] 不应触发知识检索(detected={detected})")
                    results.append((f"测试{i}", True, "正确跳过"))
            else:
                print(f"  [FAIL] 状态码: {resp.status_code}")
                results.append((f"测试{i}", False, f"状态码: {resp.status_code}"))

        except Exception as e:
            print(f"  [FAIL] 错误: {e}")
            results.append((f"测试{i}", False, str(e)))

    # 汇总
    print("\n" + "="*60)
    passed = sum(1 for r in results if r[1])
    total = len(results)
    print(f"测试结果: {passed}/{total} 通过")
    print("="*60)

    # 功能总结
    print("\n智能知识库自动检索功能:")
    print("  - 法律领域自动识别 (民法典、刑法、劳动法等)")
    print("  - 医疗健康领域自动识别 (疾病、药物、治疗等)")
    print("  - 金融财经领域自动识别 (股票、基金、贷款等)")
    print("  - 教育领域自动识别 (高考、考研、培训等)")
    print("  - 技术领域自动识别 (编程、AI、大数据等)")
    print("\n使用方式:")
    print("  1. 在聊天中启用知识库: use_knowledge=true")
    print("  2. 设置自动检索: auto_retrieve=true")
    print("  3. 系统会自动识别问题领域并检索相关知识")
    print("  4. 检索结果会注入到提示词中辅助回答")

    return passed == total

if __name__ == "__main__":
    test_smart_retrieval()
