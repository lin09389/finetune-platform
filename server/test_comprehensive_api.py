"""
Finetune Platform - Comprehensive API Test Script
"""
import requests
import json
import time
import sys
from datetime import datetime

BASE_URL = "http://127.0.0.1:8000"

class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []
        self.results = []
    
    def add_pass(self, test_name, response=None):
        self.passed += 1
        self.results.append({
            "test": test_name,
            "status": "PASS",
            "response": response
        })
        print(f"  [PASS] {test_name}")
    
    def add_fail(self, test_name, error, expected=None):
        self.failed += 1
        self.results.append({
            "test": test_name,
            "status": "FAIL",
            "error": str(error),
            "expected": expected
        })
        self.errors.append(f"{test_name}: {error}")
        print(f"  [FAIL] {test_name}: {error}")
    
    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*60}")
        print(f"Test Summary: {self.passed}/{total} passed")
        print(f"{'='*60}")
        if self.errors:
            print("\nFailed Tests:")
            for e in self.errors:
                print(f"  - {e}")
        return self.failed == 0


def test_api(method, endpoint, data=None, expected_status=200, timeout=30):
    """Generic API test helper"""
    url = f"{BASE_URL}{endpoint}"
    try:
        if method == "GET":
            resp = requests.get(url, timeout=timeout)
        elif method == "POST":
            resp = requests.post(url, json=data, timeout=timeout)
        elif method == "DELETE":
            resp = requests.delete(url, timeout=timeout)
        elif method == "PUT":
            resp = requests.put(url, json=data, timeout=timeout)
        else:
            return None, f"Unsupported method: {method}"
        
        return resp, None
    except requests.exceptions.Timeout:
        return None, "Request timeout"
    except requests.exceptions.ConnectionError:
        return None, "Connection error - server may not be running"
    except Exception as e:
        return None, str(e)


def test_root_and_health(result: TestResult):
    """Test root and health endpoints"""
    print("\n[1] Testing Root & Health Endpoints...")
    
    # Test root
    resp, err = test_api("GET", "/")
    if err:
        result.add_fail("GET /", err)
    elif resp.status_code == 200:
        data = resp.json()
        if "version" in data:
            result.add_pass("GET /", data)
        else:
            result.add_fail("GET /", "Missing version field")
    else:
        result.add_fail("GET /", f"Status {resp.status_code}")
    
    # Test health
    resp, err = test_api("GET", "/health")
    if err:
        result.add_fail("GET /health", err)
    elif resp.status_code == 200:
        data = resp.json()
        if "status" in data:
            result.add_pass("GET /health", data)
        else:
            result.add_fail("GET /health", "Missing status field")
    else:
        result.add_fail("GET /health", f"Status {resp.status_code}")


def test_device_api(result: TestResult):
    """Test device info endpoints"""
    print("\n[2] Testing Device API...")
    
    # Test device info
    resp, err = test_api("GET", "/device/info")
    if err:
        result.add_fail("GET /device/info", err)
    elif resp.status_code == 200:
        data = resp.json()
        required_fields = ["cuda_available", "device_name", "memory_total"]
        missing = [f for f in required_fields if f not in data]
        if not missing:
            result.add_pass("GET /device/info", {k: data.get(k) for k in required_fields})
        else:
            result.add_fail("GET /device/info", f"Missing fields: {missing}")
    else:
        result.add_fail("GET /device/info", f"Status {resp.status_code}")
    
    # Test VRAM info
    resp, err = test_api("GET", "/device/vram")
    if err:
        result.add_fail("GET /device/vram", err)
    elif resp.status_code == 200:
        data = resp.json()
        result.add_pass("GET /device/vram", data)
    else:
        result.add_fail("GET /device/vram", f"Status {resp.status_code}")
    
    # Test memory info
    resp, err = test_api("GET", "/device/memory")
    if err:
        result.add_fail("GET /device/memory", err)
    elif resp.status_code == 200:
        data = resp.json()
        if "virtual" in data:
            result.add_pass("GET /device/memory", data.get("virtual"))
        else:
            result.add_fail("GET /device/memory", "Missing virtual field")
    else:
        result.add_fail("GET /device/memory", f"Status {resp.status_code}")
    
    # Test disk info
    resp, err = test_api("GET", "/device/disk")
    if err:
        result.add_fail("GET /device/disk", err)
    elif resp.status_code == 200:
        data = resp.json()
        if "partitions" in data:
            result.add_pass("GET /device/disk", f"{len(data['partitions'])} partitions")
        else:
            result.add_fail("GET /device/disk", "Missing partitions field")
    else:
        result.add_fail("GET /device/disk", f"Status {resp.status_code}")


def test_models_api(result: TestResult):
    """Test models management endpoints"""
    print("\n[3] Testing Models API...")
    
    # Test list models
    resp, err = test_api("GET", "/models")
    if err:
        result.add_fail("GET /models", err)
    elif resp.status_code == 200:
        data = resp.json()
        result.add_pass("GET /models", f"{len(data) if isinstance(data, list) else 0} models")
    else:
        result.add_fail("GET /models", f"Status {resp.status_code}")
    
    # Test download status
    resp, err = test_api("GET", "/models/download/status")
    if err:
        result.add_fail("GET /models/download/status", err)
    elif resp.status_code == 200:
        data = resp.json()
        result.add_pass("GET /models/download/status", data)
    else:
        result.add_fail("GET /models/download/status", f"Status {resp.status_code}")
    
    # Test model stats (correct path)
    resp, err = test_api("GET", "/models/stats")
    if err:
        result.add_fail("GET /models/stats", err)
    elif resp.status_code == 200:
        data = resp.json()
        result.add_pass("GET /models/stats", data)
    else:
        result.add_fail("GET /models/stats", f"Status {resp.status_code}")
    
    # Test invalid model ID
    resp, err = test_api("GET", "/models/nonexistent_model_12345")
    if err:
        result.add_fail("GET /models/{invalid_id}", err)
    elif resp.status_code == 404:
        result.add_pass("GET /models/{invalid_id}", "Correctly returns 404")
    else:
        result.add_fail("GET /models/{invalid_id}", f"Expected 404, got {resp.status_code}")


def test_datasets_api(result: TestResult):
    """Test datasets management endpoints"""
    print("\n[4] Testing Datasets API...")
    
    # Test list datasets
    resp, err = test_api("GET", "/datasets")
    if err:
        result.add_fail("GET /datasets", err)
    elif resp.status_code == 200:
        data = resp.json()
        result.add_pass("GET /datasets", f"{len(data) if isinstance(data, list) else 0} datasets")
    else:
        result.add_fail("GET /datasets", f"Status {resp.status_code}")
    
    # Test invalid dataset ID
    resp, err = test_api("GET", "/datasets/nonexistent_dataset_12345")
    if err:
        result.add_fail("GET /datasets/{invalid_id}", err)
    elif resp.status_code == 404:
        result.add_pass("GET /datasets/{invalid_id}", "Correctly returns 404")
    else:
        result.add_fail("GET /datasets/{invalid_id}", f"Expected 404, got {resp.status_code}")


def test_training_api(result: TestResult):
    """Test training endpoints"""
    print("\n[5] Testing Training API...")
    
    # Test get progress
    resp, err = test_api("GET", "/training/progress")
    if err:
        result.add_fail("GET /training/progress", err)
    elif resp.status_code == 200:
        data = resp.json()
        if "status" in data:
            result.add_pass("GET /training/progress", data.get("status"))
        else:
            result.add_fail("GET /training/progress", "Missing status field")
    else:
        result.add_fail("GET /training/progress", f"Status {resp.status_code}")
    
    # Test get history
    resp, err = test_api("GET", "/training/history")
    if err:
        result.add_fail("GET /training/history", err)
    elif resp.status_code == 200:
        data = resp.json()
        result.add_pass("GET /training/history", f"{len(data) if isinstance(data, list) else 0} records")
    else:
        result.add_fail("GET /training/history", f"Status {resp.status_code}")
    
    # Test get status
    resp, err = test_api("GET", "/training/status")
    if err:
        result.add_fail("GET /training/status", err)
    elif resp.status_code == 200:
        data = resp.json()
        result.add_pass("GET /training/status", data)
    else:
        result.add_fail("GET /training/status", f"Status {resp.status_code}")
    
    # Test queue status
    resp, err = test_api("GET", "/training/queue/status")
    if err:
        result.add_fail("GET /training/queue/status", err)
    elif resp.status_code == 200:
        data = resp.json()
        result.add_pass("GET /training/queue/status", data)
    else:
        result.add_fail("GET /training/queue/status", f"Status {resp.status_code}")
    
    # Test check resources (POST method)
    resp, err = test_api("POST", "/training/check-resources", data={"model_id": "test", "dataset_id": "test"})
    if err:
        result.add_fail("POST /training/check-resources", err)
    elif resp.status_code in [200, 400, 404, 422]:
        result.add_pass("POST /training/check-resources", f"Status {resp.status_code}")
    else:
        result.add_fail("POST /training/check-resources", f"Status {resp.status_code}")
    
    # Test start training validation (should fail with missing params)
    resp, err = test_api("POST", "/training/start", data={})
    if err:
        result.add_fail("POST /training/start (empty)", err)
    elif resp.status_code == 422:
        result.add_pass("POST /training/start (empty)", "Correctly validates params")
    else:
        result.add_fail("POST /training/start (empty)", f"Expected 422, got {resp.status_code}")
    
    # Test stop training when idle
    resp, err = test_api("POST", "/training/stop")
    if err:
        result.add_fail("POST /training/stop", err)
    elif resp.status_code in [200, 400]:
        result.add_pass("POST /training/stop", f"Status {resp.status_code}")
    else:
        result.add_fail("POST /training/stop", f"Unexpected status {resp.status_code}")


def test_inference_api(result: TestResult):
    """Test inference endpoints"""
    print("\n[6] Testing Inference API...")
    
    # Test get backends
    resp, err = test_api("GET", "/inference/backends")
    if err:
        result.add_fail("GET /inference/backends", err)
    elif resp.status_code == 200:
        data = resp.json()
        result.add_pass("GET /inference/backends", data)
    else:
        result.add_fail("GET /inference/backends", f"Status {resp.status_code}")
    
    # Test get inference models
    resp, err = test_api("GET", "/inference/models")
    if err:
        result.add_fail("GET /inference/models", err)
    elif resp.status_code == 200:
        data = resp.json()
        result.add_pass("GET /inference/models", f"{len(data) if isinstance(data, list) else 0} models")
    else:
        result.add_fail("GET /inference/models", f"Status {resp.status_code}")
    
    # Test ollama status
    resp, err = test_api("GET", "/inference/ollama/status")
    if err:
        result.add_fail("GET /inference/ollama/status", err)
    elif resp.status_code == 200:
        data = resp.json()
        result.add_pass("GET /inference/ollama/status", f"running={data.get('running', False)}")
    else:
        result.add_fail("GET /inference/ollama/status", f"Status {resp.status_code}")
    
    # Test cache status
    resp, err = test_api("GET", "/inference/cache/status")
    if err:
        result.add_fail("GET /inference/cache/status", err)
    elif resp.status_code == 200:
        data = resp.json()
        result.add_pass("GET /inference/cache/status", data)
    else:
        result.add_fail("GET /inference/cache/status", f"Status {resp.status_code}")
    
    # Test merge status
    resp, err = test_api("GET", "/inference/merge/status")
    if err:
        result.add_fail("GET /inference/merge/status", err)
    elif resp.status_code == 200:
        data = resp.json()
        result.add_pass("GET /inference/merge/status", data)
    else:
        result.add_fail("GET /inference/merge/status", f"Status {resp.status_code}")
    
    # Test generate validation (empty prompt should fail)
    resp, err = test_api("POST", "/inference/generate", data={"model_id": "test", "prompt": ""})
    if err:
        result.add_fail("POST /inference/generate (empty)", err)
    elif resp.status_code in [400, 422, 404]:
        result.add_pass("POST /inference/generate (empty)", "Correctly validates input")
    else:
        result.add_fail("POST /inference/generate (empty)", f"Status {resp.status_code}")


def test_chat_history_api(result: TestResult):
    """Test chat history endpoints"""
    print("\n[7] Testing Chat History API...")
    
    # Test get history
    resp, err = test_api("GET", "/chat/history")
    if err:
        result.add_fail("GET /chat/history", err)
    elif resp.status_code == 200:
        data = resp.json()
        result.add_pass("GET /chat/history", f"{len(data) if isinstance(data, list) else 0} sessions")
    else:
        result.add_fail("GET /chat/history", f"Status {resp.status_code}")
    
    # Test get stats
    resp, err = test_api("GET", "/chat/stats")
    if err:
        result.add_fail("GET /chat/stats", err)
    elif resp.status_code == 200:
        data = resp.json()
        result.add_pass("GET /chat/stats", data)
    else:
        result.add_fail("GET /chat/stats", f"Status {resp.status_code}")
    
    # Test create session
    resp, err = test_api("POST", "/chat/session", data={"title": "Test Session", "model_id": "test"})
    if err:
        result.add_fail("POST /chat/session", err)
    elif resp.status_code == 200:
        data = resp.json()
        session_id = data.get("id")
        result.add_pass("POST /chat/session", f"Created session: {session_id}")
        
        # Test get session
        if session_id:
            resp2, err2 = test_api("GET", f"/chat/session/{session_id}")
            if err2:
                result.add_fail("GET /chat/session/{id}", err2)
            elif resp2.status_code == 200:
                result.add_pass("GET /chat/session/{id}", "Session retrieved")
            else:
                result.add_fail("GET /chat/session/{id}", f"Status {resp2.status_code}")
            
            # Test delete session
            resp3, err3 = test_api("DELETE", f"/chat/session/{session_id}")
            if err3:
                result.add_fail("DELETE /chat/session/{id}", err3)
            elif resp3.status_code == 200:
                result.add_pass("DELETE /chat/session/{id}", "Session deleted")
            else:
                result.add_fail("DELETE /chat/session/{id}", f"Status {resp3.status_code}")
    else:
        result.add_fail("POST /chat/session", f"Status {resp.status_code}")


def test_rag_api(result: TestResult):
    """Test RAG knowledge base endpoints"""
    print("\n[8] Testing RAG API...")
    
    # Test list collections
    resp, err = test_api("GET", "/rag/collections")
    if err:
        result.add_fail("GET /rag/collections", err)
    elif resp.status_code == 200:
        data = resp.json()
        result.add_pass("GET /rag/collections", data)
    else:
        result.add_fail("GET /rag/collections", f"Status {resp.status_code}")


def test_context_api(result: TestResult):
    """Test project context endpoints"""
    print("\n[9] Testing Context API...")
    
    # Test list projects
    resp, err = test_api("GET", "/context/projects")
    if err:
        result.add_fail("GET /context/projects", err)
    elif resp.status_code == 200:
        data = resp.json()
        result.add_pass("GET /context/projects", data)
    else:
        result.add_fail("GET /context/projects", f"Status {resp.status_code}")


def test_agent_api(result: TestResult):
    """Test agent endpoints"""
    print("\n[10] Testing Agent API...")
    
    # Test get capabilities
    resp, err = test_api("GET", "/agent/capabilities")
    if err:
        result.add_fail("GET /agent/capabilities", err)
    elif resp.status_code == 200:
        data = resp.json()
        result.add_pass("GET /agent/capabilities", f"{len(data.get('actions', []))} actions")
    else:
        result.add_fail("GET /agent/capabilities", f"Status {resp.status_code}")
    
    # Test audit stats
    resp, err = test_api("GET", "/agent/audit/stats")
    if err:
        result.add_fail("GET /agent/audit/stats", err)
    elif resp.status_code == 200:
        data = resp.json()
        result.add_pass("GET /agent/audit/stats", data)
    else:
        result.add_fail("GET /agent/audit/stats", f"Status {resp.status_code}")
    
    # Test detect intent
    resp, err = test_api("POST", "/agent/detect-intent", data={"message": "Hello, how are you?"})
    if err:
        result.add_fail("POST /agent/detect-intent", err)
    elif resp.status_code == 200:
        data = resp.json()
        result.add_pass("POST /agent/detect-intent", f"detected={data.get('detected', False)}")
    else:
        result.add_fail("POST /agent/detect-intent", f"Status {resp.status_code}")


def test_skills_api(result: TestResult):
    """Test skills endpoints"""
    print("\n[11] Testing Skills API...")
    
    # Test list skills
    resp, err = test_api("GET", "/skills")
    if err:
        result.add_fail("GET /skills", err)
    elif resp.status_code == 200:
        data = resp.json()
        skills = data.get("skills", [])
        result.add_pass("GET /skills", f"{len(skills)} skills")
    else:
        result.add_fail("GET /skills", f"Status {resp.status_code}")
    
    # Test skills stats
    resp, err = test_api("GET", "/skills/stats")
    if err:
        result.add_fail("GET /skills/stats", err)
    elif resp.status_code == 200:
        data = resp.json()
        result.add_pass("GET /skills/stats", data)
    else:
        result.add_fail("GET /skills/stats", f"Status {resp.status_code}")
    
    # Test list categories
    resp, err = test_api("GET", "/skills/categories")
    if err:
        result.add_fail("GET /skills/categories", err)
    elif resp.status_code == 200:
        data = resp.json()
        result.add_pass("GET /skills/categories", f"{len(data)} categories")
    else:
        result.add_fail("GET /skills/categories", f"Status {resp.status_code}")


def test_workspace_api(result: TestResult):
    """Test workspace endpoints"""
    print("\n[12] Testing Workspace API...")
    
    # Test list workspaces (correct path)
    resp, err = test_api("GET", "/workspace/workspaces")
    if err:
        result.add_fail("GET /workspace/workspaces", err)
    elif resp.status_code == 200:
        data = resp.json()
        result.add_pass("GET /workspace/workspaces", f"{len(data) if isinstance(data, list) else 0} workspaces")
    else:
        result.add_fail("GET /workspace/workspaces", f"Status {resp.status_code}")


def test_memory_api(result: TestResult):
    """Test memory endpoints"""
    print("\n[13] Testing Memory API...")
    
    # Test list memories (correct path)
    resp, err = test_api("GET", "/memory/list")
    if err:
        result.add_fail("GET /memory/list", err)
    elif resp.status_code == 200:
        data = resp.json()
        result.add_pass("GET /memory/list", data)
    else:
        result.add_fail("GET /memory/list", f"Status {resp.status_code}")
    
    # Test memory stats
    resp, err = test_api("GET", "/memory/stats")
    if err:
        result.add_fail("GET /memory/stats", err)
    elif resp.status_code == 200:
        data = resp.json()
        result.add_pass("GET /memory/stats", data)
    else:
        result.add_fail("GET /memory/stats", f"Status {resp.status_code}")


def test_sessions_api(result: TestResult):
    """Test sessions endpoints"""
    print("\n[14] Testing Sessions API...")
    
    # Test list sessions
    resp, err = test_api("GET", "/sessions")
    if err:
        result.add_fail("GET /sessions", err)
    elif resp.status_code == 200:
        data = resp.json()
        result.add_pass("GET /sessions", data)
    else:
        result.add_fail("GET /sessions", f"Status {resp.status_code}")


def test_cloud_chat_api(result: TestResult):
    """Test cloud chat endpoints"""
    print("\n[15] Testing Cloud Chat API...")
    
    # Test list providers
    resp, err = test_api("GET", "/cloud/providers")
    if err:
        result.add_fail("GET /cloud/providers", err)
    elif resp.status_code == 200:
        data = resp.json()
        result.add_pass("GET /cloud/providers", data)
    else:
        result.add_fail("GET /cloud/providers", f"Status {resp.status_code}")


def test_error_handling(result: TestResult):
    """Test error handling"""
    print("\n[16] Testing Error Handling...")
    
    # Test 404 for non-existent endpoint
    resp, err = test_api("GET", "/nonexistent_endpoint_12345")
    if err:
        result.add_fail("GET /nonexistent (404 test)", err)
    elif resp.status_code == 404:
        result.add_pass("GET /nonexistent (404 test)", "Correctly returns 404")
    else:
        result.add_fail("GET /nonexistent (404 test)", f"Expected 404, got {resp.status_code}")
    
    # Test invalid JSON
    try:
        resp = requests.post(f"{BASE_URL}/training/start", data="invalid json", timeout=10)
        if resp.status_code >= 400:
            result.add_pass("POST invalid JSON", f"Correctly rejects with {resp.status_code}")
        else:
            result.add_fail("POST invalid JSON", "Should reject invalid JSON")
    except Exception as e:
        result.add_pass("POST invalid JSON", f"Correctly rejects: {str(e)[:50]}")


def main():
    print("="*60)
    print("Finetune Platform - Comprehensive API Test")
    print(f"Started: {datetime.now().isoformat()}")
    print(f"Base URL: {BASE_URL}")
    print("="*60)
    
    result = TestResult()
    
    try:
        test_root_and_health(result)
        test_device_api(result)
        test_models_api(result)
        test_datasets_api(result)
        test_training_api(result)
        test_inference_api(result)
        test_chat_history_api(result)
        test_rag_api(result)
        test_context_api(result)
        test_agent_api(result)
        test_skills_api(result)
        test_workspace_api(result)
        test_memory_api(result)
        test_sessions_api(result)
        test_cloud_chat_api(result)
        test_error_handling(result)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    except Exception as e:
        print(f"\n\nTest suite error: {e}")
    
    success = result.summary()
    
    # Save report
    report = {
        "timestamp": datetime.now().isoformat(),
        "base_url": BASE_URL,
        "summary": {
            "total": result.passed + result.failed,
            "passed": result.passed,
            "failed": result.failed,
            "success_rate": f"{result.passed / (result.passed + result.failed) * 100:.1f}%" if (result.passed + result.failed) > 0 else "0%"
        },
        "results": result.results
    }
    
    report_path = "test_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\nReport saved to: {report_path}")
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
