"""
功能验证测试脚本 - 测试模型输出、技能调用、记忆系统、Agent操作
"""
import requests
import json
import time
from datetime import datetime

BASE_URL = "http://127.0.0.1:8000"

class TestResult:
    def __init__(self):
        self.results = []
        self.passed = 0
        self.failed = 0
    
    def add(self, category, test_name, success, detail=""):
        self.results.append({
            "category": category,
            "test": test_name,
            "success": success,
            "detail": detail,
            "time": datetime.now().isoformat()
        })
        if success:
            self.passed += 1
            print(f"  [PASS] {test_name}")
        else:
            self.failed += 1
            print(f"  [FAIL] {test_name}: {detail}")
    
    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*60}")
        print(f"测试结果: {self.passed}/{total} 通过")
        print(f"{'='*60}")
        return self.failed == 0


def test_inference(result: TestResult):
    """测试模型推理功能"""
    print("\n[1] 测试模型推理功能...")
    
    # 测试获取推理后端
    try:
        resp = requests.get(f"{BASE_URL}/inference/backends", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            result.add("推理", "获取推理后端", True, str(data))
        else:
            result.add("推理", "获取推理后端", False, f"状态码: {resp.status_code}")
    except Exception as e:
        result.add("推理", "获取推理后端", False, str(e))
    
    # 测试获取可用模型
    try:
        resp = requests.get(f"{BASE_URL}/inference/models", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            model_count = len(data) if isinstance(data, list) else 0
            result.add("推理", f"获取可用模型 ({model_count}�?", True, str(data)[:100])
        else:
            result.add("推理", "获取可用模型", False, f"状态码: {resp.status_code}")
    except Exception as e:
        result.add("推理", "获取可用模型", False, str(e))
    
    # 测试Ollama状�?    try:
        resp = requests.get(f"{BASE_URL}/inference/ollama/status", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            running = data.get("running", False)
            model_count = len(data.get("models", []))
            result.add("推理", f"Ollama状�?(running={running}, {model_count}个模�?", True)
        else:
            result.add("推理", "Ollama状�?, False, f"状态码: {resp.status_code}")
    except Exception as e:
        result.add("推理", "Ollama状�?, False, str(e))
    
    # 测试推理生成 (如果Ollama可用)
    try:
        resp = requests.get(f"{BASE_URL}/inference/ollama/status", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("running") and data.get("models"):
                model_name = data["models"][0].get("name", "")
                if model_name:
                    # 测试简单推�?                    gen_resp = requests.post(
                        f"{BASE_URL}/inference/generate",
                        json={
                            "model_id": model_name,
                            "prompt": "你好，请回复'测试成功'",
                            "max_tokens": 50,
                            "backend": "ollama"
                        },
                        timeout=60
                    )
                    if gen_resp.status_code == 200:
                        gen_data = gen_resp.json()
                        text = gen_data.get("text", "")
                        result.add("推理", f"推理生成测试", True, f"响应: {text[:50]}...")
                    else:
                        result.add("推理", "推理生成测试", False, f"状态码: {gen_resp.status_code}")
                else:
                    result.add("推理", "推理生成测试", False, "无可用模�?)
            else:
                result.add("推理", "推理生成测试", False, "Ollama未运行或无模�?)
    except Exception as e:
        result.add("推理", "推理生成测试", False, str(e))


def test_skills(result: TestResult):
    """测试技能调用功�?""
    print("\n[2] 测试技能调用功�?..")
    
    # 测试获取技能列�?    try:
        resp = requests.get(f"{BASE_URL}/skills", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            skills = data.get("skills", [])
            result.add("技�?, f"获取技能列�?({len(skills)}�?", True)
        else:
            result.add("技�?, "获取技能列�?, False, f"状态码: {resp.status_code}")
    except Exception as e:
        result.add("技�?, "获取技能列�?, False, str(e))
    
    # 测试技能统�?    try:
        resp = requests.get(f"{BASE_URL}/skills/stats", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            result.add("技�?, "获取技能统�?, True, str(data))
        else:
            result.add("技�?, "获取技能统�?, False, f"状态码: {resp.status_code}")
    except Exception as e:
        result.add("技�?, "获取技能统�?, False, str(e))
    
    # 测试技能分�?    try:
        resp = requests.get(f"{BASE_URL}/skills/categories", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            result.add("技�?, f"获取技能分�?({len(data)}�?", True)
        else:
            result.add("技�?, "获取技能分�?, False, f"状态码: {resp.status_code}")
    except Exception as e:
        result.add("技�?, "获取技能分�?, False, str(e))
    
    # 测试技能执�?- 计算�?    try:
        resp = requests.post(
            f"{BASE_URL}/skills/execute",
            json={
                "skill_name": "calculator",
                "parameters": {"expression": "2+2"}
            },
            timeout=30
        )
        if resp.status_code == 200:
            data = resp.json()
            result.add("技�?, "计算器技能执�?, data.get("success", False), str(data))
        else:
            result.add("技�?, "计算器技能执�?, False, f"状态码: {resp.status_code}")
    except Exception as e:
        result.add("技�?, "计算器技能执�?, False, str(e))
    
    # 测试技能执�?- 系统信息
    try:
        resp = requests.post(
            f"{BASE_URL}/skills/execute",
            json={
                "skill_name": "system_info",
                "parameters": {}
            },
            timeout=30
        )
        if resp.status_code == 200:
            data = resp.json()
            result.add("技�?, "系统信息技能执�?, data.get("success", False), str(data)[:100])
        else:
            result.add("技�?, "系统信息技能执�?, False, f"状态码: {resp.status_code}")
    except Exception as e:
        result.add("技�?, "系统信息技能执�?, False, str(e))


def test_memory(result: TestResult):
    """测试记忆系统功能"""
    print("\n[3] 测试记忆系统功能...")
    
    # 测试获取记忆列表
    try:
        resp = requests.get(f"{BASE_URL}/memory/list", timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            count = data.get("count", 0)
            result.add("记忆", f"获取记忆列表 ({count}�?", True)
        else:
            result.add("记忆", "获取记忆列表", False, f"状态码: {resp.status_code}")
    except Exception as e:
        result.add("记忆", "获取记忆列表", False, str(e))
    
    # 测试记忆统计
    try:
        resp = requests.get(f"{BASE_URL}/memory/stats", timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            result.add("记忆", "获取记忆统计", True, str(data))
        else:
            result.add("记忆", "获取记忆统计", False, f"状态码: {resp.status_code}")
    except Exception as e:
        result.add("记忆", "获取记忆统计", False, str(e))
    
    # 测试记忆提取 (增加超时时间)
    try:
        resp = requests.post(
            f"{BASE_URL}/memory/extract",
            json={
                "message": "我叫张三，我喜欢编程和打篮球",
                "role": "user"
            },
            timeout=120  # 增加超时时间
        )
        if resp.status_code == 200:
            data = resp.json()
            extracted = data.get("extracted", 0)
            result.add("记忆", f"记忆提取 ({extracted}�?", True, str(data))
        else:
            result.add("记忆", "记忆提取", False, f"状态码: {resp.status_code}")
    except Exception as e:
        result.add("记忆", "记忆提取", False, str(e))
    
    # 测试记忆检�?(增加超时时间)
    try:
        resp = requests.post(
            f"{BASE_URL}/memory/recall",
            json={
                "query": "用户叫什么名�?,
                "top_k": 3
            },
            timeout=120  # 增加超时时间
        )
        if resp.status_code == 200:
            data = resp.json()
            count = data.get("count", 0)
            result.add("记忆", f"记忆检�?({count}条匹�?", True)
        else:
            result.add("记忆", "记忆检�?, False, f"状态码: {resp.status_code}")
    except Exception as e:
        result.add("记忆", "记忆检�?, False, str(e))
    
    # 测试记忆上下�?(增加超时时间)
    try:
        resp = requests.get(
            f"{BASE_URL}/memory/context",
            params={"query": "用户信息", "max_memories": 5},
            timeout=120  # 增加超时时间
        )
        if resp.status_code == 200:
            data = resp.json()
            context = data.get("context", "")
            result.add("记忆", "记忆上下文获�?, True, context[:50] if context else "无上下文")
        else:
            result.add("记忆", "记忆上下文获�?, False, f"状态码: {resp.status_code}")
    except Exception as e:
        result.add("记忆", "记忆上下文获�?, False, str(e))


def test_agent(result: TestResult):
    """测试Agent操作功能"""
    print("\n[4] 测试Agent操作功能...")
    
    # 测试获取Agent能力
    try:
        resp = requests.get(f"{BASE_URL}/agent/capabilities", timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            actions = data.get("actions", [])
            result.add("Agent", f"获取Agent能力 ({len(actions)}种操�?", True)
        else:
            result.add("Agent", "获取Agent能力", False, f"状态码: {resp.status_code}")
    except Exception as e:
        result.add("Agent", "获取Agent能力", False, str(e))
    
    # 测试审计统计
    try:
        resp = requests.get(f"{BASE_URL}/agent/audit/stats", timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            result.add("Agent", "获取审计统计", True, str(data))
        else:
            result.add("Agent", "获取审计统计", False, f"状态码: {resp.status_code}")
    except Exception as e:
        result.add("Agent", "获取审计统计", False, str(e))
    
    # 测试意图检�?    try:
        resp = requests.post(
            f"{BASE_URL}/agent/detect-intent",
            json={"message": "帮我列出当前目录的文�?},
            timeout=30
        )
        if resp.status_code == 200:
            data = resp.json()
            detected = data.get("detected", False)
            result.add("Agent", f"意图检�?(detected={detected})", True, str(data))
        else:
            result.add("Agent", "意图检�?, False, f"状态码: {resp.status_code}")
    except Exception as e:
        result.add("Agent", "意图检�?, False, str(e))
    
    # 测试Agent执行 - 列出目录
    try:
        resp = requests.post(
            f"{BASE_URL}/agent/execute",
            json={
                "action": "file_list",
                "params": {"directory": "."},
                "confirm": False
            },
            timeout=30
        )
        if resp.status_code == 200:
            data = resp.json()
            success = data.get("success", False)
            result.add("Agent", "执行文件列表操作", success, str(data)[:100])
        else:
            result.add("Agent", "执行文件列表操作", False, f"状态码: {resp.status_code}")
    except Exception as e:
        result.add("Agent", "执行文件列表操作", False, str(e))
    
    # 测试Agent执行 - 系统信息
    try:
        resp = requests.post(
            f"{BASE_URL}/agent/execute",
            json={
                "action": "system_info",
                "params": {},
                "confirm": False
            },
            timeout=30
        )
        if resp.status_code == 200:
            data = resp.json()
            success = data.get("success", False)
            result.add("Agent", "执行系统信息操作", success, str(data)[:100])
        else:
            result.add("Agent", "执行系统信息操作", False, f"状态码: {resp.status_code}")
    except Exception as e:
        result.add("Agent", "执行系统信息操作", False, str(e))


def test_chat_integration(result: TestResult):
    """测试聊天集成功能"""
    print("\n[5] 测试聊天集成功能...")
    
    # 测试聊天历史
    try:
        resp = requests.get(f"{BASE_URL}/chat/history", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            result.add("聊天", f"获取聊天历史 ({len(data)}个会�?", True)
        else:
            result.add("聊天", "获取聊天历史", False, f"状态码: {resp.status_code}")
    except Exception as e:
        result.add("聊天", "获取聊天历史", False, str(e))
    
    # 测试创建会话
    try:
        resp = requests.post(
            f"{BASE_URL}/chat/session",
            json={"title": "功能测试会话", "model_id": "test"},
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            session_id = data.get("id")
            result.add("聊天", f"创建会话 ({session_id})", True)
            
            # 测试添加消息
            if session_id:
                msg_resp = requests.post(
                    f"{BASE_URL}/chat/session/{session_id}/message",
                    json={"messages": [{"id": "test_msg", "role": "user", "content": "测试消息", "timestamp": datetime.now().isoformat()}]},
                    timeout=10
                )
                if msg_resp.status_code == 200:
                    result.add("聊天", "添加消息", True)
                else:
                    result.add("聊天", "添加消息", False, f"状态码: {msg_resp.status_code}")
                
                # 清理测试会话
                requests.delete(f"{BASE_URL}/chat/session/{session_id}", timeout=5)
        else:
            result.add("聊天", "创建会话", False, f"状态码: {resp.status_code}")
    except Exception as e:
        result.add("聊天", "创建会话", False, str(e))


def main():
    print("="*60)
    print("Finetune Platform 功能验证测试")
    print(f"测试时间: {datetime.now().isoformat()}")
    print(f"服务地址: {BASE_URL}")
    print("="*60)
    
    result = TestResult()
    
    # 检查服务是否运�?    try:
        resp = requests.get(f"{BASE_URL}/health", timeout=5)
        if resp.status_code != 200:
            print(f"错误: 服务未正常运�?(状态码: {resp.status_code})")
            return 1
        print(f"服务状�? 正常")
    except Exception as e:
        print(f"错误: 无法连接到服�?- {e}")
        return 1
    
    test_inference(result)
    test_skills(result)
    test_memory(result)
    test_agent(result)
    test_chat_integration(result)
    
    success = result.summary()
    
    # 保存报告
    report = {
        "timestamp": datetime.now().isoformat(),
        "base_url": BASE_URL,
        "summary": {
            "total": result.passed + result.failed,
            "passed": result.passed,
            "failed": result.failed
        },
        "results": result.results
    }
    
    with open("功能验证测试报告.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    print(f"\n报告已保�? 功能验证测试报告.json")
    
    return 0 if success else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
