"""
HuggingFace 镜像源测试脚本
"""
import time
from typing import Any

import requests

MIRRORS = {
    "official": "https://huggingface.co",
    "hf-mirror": "https://hf-mirror.com",
    "aliyun": "https://mirrors.aliyun.com/huggingface",
}

def test_mirror(name: str, base_url: str, model_id: str = "bert-base-uncased") -> dict[str, Any]:
    """测试镜像源连接"""
    result = {
        "name": name,
        "url": base_url,
        "status": "unknown",
        "latency": 0,
        "error": None,
    }

    test_url = f"{base_url}/{model_id}/resolve/main/config.json"

    try:
        start = time.time()
        response = requests.head(test_url, timeout=10, allow_redirects=True)
        latency = (time.time() - start) * 1000

        result["latency"] = round(latency, 2)

        if response.status_code == 200:
            result["status"] = "ok"
        elif response.status_code == 404:
            result["status"] = "partial"
            result["error"] = "Model not found (but mirror is reachable)"
        else:
            result["status"] = "error"
            result["error"] = f"HTTP {response.status_code}"

    except requests.exceptions.Timeout:
        result["status"] = "timeout"
        result["error"] = "Connection timeout (>10s)"
    except requests.exceptions.ConnectionError as e:
        result["status"] = "failed"
        result["error"] = str(e)
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)

    return result


def main():
    print("=" * 60)
    print("HuggingFace 镜像源测试")
    print("=" * 60)

    print("\n测试各镜像源连接速度...\n")

    results = []

    for name, url in MIRRORS.items():
        print(f"测试 {name} ({url})...", end=" ", flush=True)
        result = test_mirror(name, url)
        results.append(result)

        if result["status"] == "ok":
            print(f"[OK] {result['latency']}ms")
        elif result["status"] == "partial":
            print(f"[PARTIAL] {result['latency']}ms - {result['error']}")
        elif result["status"] == "timeout":
            print("[TIMEOUT] >10s")
        else:
            print(f"[FAILED] {result['error']}")

    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)

    best = None
    best_latency = float("inf")

    for r in results:
        status_icon = {
            "ok": "[OK]",
            "partial": "[PARTIAL]",
            "timeout": "[TIMEOUT]",
            "failed": "[FAILED]",
            "error": "[ERROR]",
        }.get(r["status"], "[?]")

        latency_str = f"{r['latency']}ms" if r['latency'] > 0 else "N/A"

        print(f"{status_icon} {r['name']:12} | {latency_str:>8} | {r['url']}")

        if r["status"] == "ok" and r["latency"] < best_latency:
            best_latency = r["latency"]
            best = r

    if best:
        print(f"\n推荐镜像源: {best['name']} ({best['url']})")
        print("\n设置方法:")
        print(f"  export HF_ENDPOINT={best['url']}")
        print("  或在 .env 文件中设置:")
        print(f"  HF_ENDPOINT={best['url']}")
    else:
        print("\n警告: 所有镜像源均不可用，请检查网络连接")

    return results


if __name__ == "__main__":
    main()
