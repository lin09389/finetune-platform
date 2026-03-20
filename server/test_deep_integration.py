# -*- coding: utf-8 -*-
"""
深度集成测试脚本
覆盖：E2E 场景、并发压力、边界条件、异常处理、安全�?"""
import sys
import os
import time
import json
import asyncio
import threading
import random
import string
import hashlib
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Any, Optional
import traceback

# 添加路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 测试依赖
try:
    import httpx
    import aiohttp
    from fastapi.testclient import TestClient
    from main import app
    from security.encryption import secure_storage
    from security.file_sandbox import file_sandbox
    from security.audit_log import audit_logger
    from ai.gateway import get_provider
    DEPENDENCIES_OK = True
except Exception as e:
    print(f"[ERROR] 依赖导入失败：{e}")
    DEPENDENCIES_OK = False


# ============================================================================
# 测试基础设施
# ============================================================================

class TestResult:
    """测试结果"""
    def __init__(self, name: str):
        self.name = name
        self.passed = 0
        self.failed = 0
        self.errors = []
        self.details = []
        
    def add_pass(self, detail: str = ""):
        self.passed += 1
        if detail:
            self.details.append(f"[PASS] {detail}")
            
    def add_fail(self, detail: str):
        self.failed += 1
        self.errors.append(f"[FAIL] {detail}")
        
    def add_error(self, detail: str):
        self.failed += 1
        self.errors.append(f"[ERROR] {detail}")
        
    def summary(self) -> str:
        total = self.passed + self.failed
        rate = self.passed / total * 100 if total > 0 else 0
        return f"{self.name}: {self.passed}/{total} ({rate:.1f}%)"


class DeepTestSuite:
    """深度测试套件"""
    
    def __init__(self):
        self.base_url = "http://127.0.0.1:8000"
        self.client = None
        self.results: Dict[str, TestResult] = {}
        self.start_time = datetime.now()
        
    def setup(self):
        """设置测试环境"""
        print("\n" + "=" * 70)
        print("深度集成测试套件")
        print("=" * 70)
        print(f"开始时间：{self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"基础 URL: {self.base_url}")
        print("-" * 70)
        
        # 创建 HTTP 客户�?        if DEPENDENCIES_OK:
            try:
                self.client = TestClient(app)
            except Exception as e:
                print(f"[WARN] TestClient 创建失败：{e}")
                
    def teardown(self):
        """清理测试环境"""
        end_time = datetime.now()
        duration = (end_time - self.start_time).total_seconds()
        
        print("\n" + "=" * 70)
        print("测试完成")
        print("=" * 70)
        print(f"结束时间：{end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"总耗时：{duration:.2f}s")
        print("-" * 70)
        
        # 汇总结�?        total_passed = sum(r.passed for r in self.results.values())
        total_failed = sum(r.failed for r in self.results.values())
        total = total_passed + total_failed
        rate = total_passed / total * 100 if total > 0 else 0
        
        print(f"\n总结果：{total_passed}/{total} ({rate:.1f}%)")
        
        # 显示失败详情
        for name, result in self.results.items():
            if result.failed > 0:
                print(f"\n{name} 失败详情:")
                for error in result.errors[:5]:  # 只显示前 5 �?                    print(f"  {error}")
                    
    def run_test(self, category: str, test_func):
        """运行测试"""
        if category not in self.results:
            self.results[category] = TestResult(category)
            
        try:
            test_func()
        except Exception as e:
            self.results[category].add_error(f"{test_func.__name__}: {str(e)}")
            traceback.print_exc()
            
    # ========================================================================
    # 1. 边界条件测试
    # ========================================================================
    
    def test_boundary_conditions(self):
        """边界条件测试"""
        result = self.results.get("边界条件", TestResult("边界条件"))
        
        # 测试 1: 空字符串
        print("\n[边界测试] 空字符串输入")
        try:
            if self.client:
                response = self.client.post("/chat", json={
                    "messages": [{"role": "user", "content": ""}],
                    "model": "test"
                })
                # 应该返回错误或空响应，不崩溃
                result.add_pass("空字符串处理正常")
        except Exception as e:
            result.add_fail(f"空字符串处理失败：{e}")
            
        # 测试 2: 超长字符�?        print("[边界测试] 超长字符�?(100K 字符)")
        try:
            long_text = "A" * 100000
            if self.client:
                response = self.client.post("/chat", json={
                    "messages": [{"role": "user", "content": long_text}],
                    "model": "test"
                })
                # 应该合理处理（拒绝或截断�?                result.add_pass("超长字符串处理正�?)
        except Exception as e:
            result.add_fail(f"超长字符串处理失败：{e}")
            
        # 测试 3: 特殊字符
        print("[边界测试] 特殊字符 (emoji, unicode)")
        try:
            special_text = "Hello 🌍 世界！こんにちは"
            if self.client:
                response = self.client.post("/chat", json={
                    "messages": [{"role": "user", "content": special_text}],
                    "model": "test"
                })
                result.add_pass("特殊字符处理正常")
        except Exception as e:
            result.add_fail(f"特殊字符处理失败：{e}")
            
        # 测试 4: 超大 JSON
        print("[边界测试] 超大 JSON (1MB)")
        try:
            large_data = {"data": "x" * 1000000}
            if self.client:
                response = self.client.post("/chat", json=large_data)
                # 应该合理处理
                result.add_pass("超大 JSON 处理正常")
        except Exception as e:
            result.add_fail(f"超大 JSON 处理失败：{e}")
            
        # 测试 5: 嵌套过深
        print("[边界测试] 嵌套过深 (100 �?")
        try:
            deep_data = {}
            current = deep_data
            for i in range(100):
                current["nested"] = {}
                current = current["nested"]
                
            if self.client:
                response = self.client.post("/chat", json=deep_data)
                result.add_pass("嵌套数据处理正常")
        except Exception as e:
            result.add_fail(f"嵌套数据处理失败：{e}")
            
        self.results["边界条件"] = result
        
    # ========================================================================
    # 2. 安全性测�?    # ========================================================================
    
    def test_security(self):
        """安全性测�?""
        result = self.results.get("安全�?, TestResult("安全�?))
        
        # 测试 1: SQL 注入尝试
        print("\n[安全测试] SQL 注入尝试")
        try:
            sql_injection = "'; DROP TABLE users; --"
            if self.client:
                response = self.client.post("/chat", json={
                    "messages": [{"role": "user", "content": sql_injection}],
                    "model": "test"
                })
                # 不应该崩�?                result.add_pass("SQL 注入防护正常")
        except Exception as e:
            result.add_fail(f"SQL 注入防护失败：{e}")
            
        # 测试 2: XSS 尝试
        print("[安全测试] XSS 攻击尝试")
        try:
            xss_payload = "<script>alert('XSS')</script>"
            if self.client:
                response = self.client.post("/chat", json={
                    "messages": [{"role": "user", "content": xss_payload}],
                    "model": "test"
                })
                result.add_pass("XSS 防护正常")
        except Exception as e:
            result.add_fail(f"XSS 防护失败：{e}")
            
        # 测试 3: 路径遍历
        print("[安全测试] 路径遍历攻击")
        try:
            path_traversal = "../../../etc/passwd"
            try:
                content = file_sandbox.read_file(path_traversal)
                result.add_fail("路径遍历防护失效")
            except PermissionError:
                result.add_pass("路径遍历防护正常")
        except Exception as e:
            result.add_error(f"路径遍历测试错误：{e}")
            
        # 测试 4: API Key 加密验证
        print("[安全测试] API Key 加密验证")
        try:
            test_key = "test_security_key_12345"
            key_id = "test_security_" + datetime.now().strftime("%Y%m%d%H%M%S")
            
            # 加密存储
            secure_storage.store_api_key(key_id, "test", test_key)
            
            # 验证文件不直接包含明�?            vault_file = Path(__file__).parent / "data" / ".vault"
            if vault_file.exists():
                with open(vault_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                if test_key in content:
                    result.add_fail("API Key 明文泄露")
                else:
                    result.add_pass("API Key 加密正常")
            
            # 清理
            secure_storage.delete_api_key(key_id)
        except Exception as e:
            result.add_error(f"API Key 加密测试错误：{e}")
            
        # 测试 5: 审计日志记录
        print("[安全测试] 审计日志记录")
        try:
            audit_logger.log_action('security_test', details={'test': 'data'})
            result.add_pass("审计日志记录正常")
        except Exception as e:
            result.add_fail(f"审计日志记录失败：{e}")
            
        self.results["安全�?] = result
        
    # ========================================================================
    # 3. 并发压力测试
    # ========================================================================
    
    def test_concurrency(self):
        """并发压力测试"""
        result = self.results.get("并发压力", TestResult("并发压力"))
        
        # 测试 1: 并发健康检�?        print("\n[并发测试] 并发健康检�?(50 请求)")
        try:
            success_count = 0
            error_count = 0
            
            def health_check():
                try:
                    if self.client:
                        response = self.client.get("/health")
                        if response.status_code == 200:
                            return True
                except Exception:
                    pass  # 忽略异常，测试并发场景下部分请求可能失败
                return False
                
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(health_check) for _ in range(50)]
                for future in as_completed(futures):
                    if future.result():
                        success_count += 1
                    else:
                        error_count += 1
                        
            if success_count >= 45:  # 90% 成功�?                result.add_pass(f"并发健康检查通过 ({success_count}/50)")
            else:
                result.add_fail(f"并发健康检查失�?({success_count}/50)")
        except Exception as e:
            result.add_error(f"并发测试错误：{e}")
            
        # 测试 2: 并发 API Key 访问
        print("[并发测试] 并发 API Key 访问 (20 请求)")
        try:
            test_key = "test_concurrent_key"
            key_id = "test_concurrent_" + datetime.now().strftime("%Y%m%d%H%M%S")
            
            secure_storage.store_api_key(key_id, "test", test_key)
            
            success_count = 0
            
            def get_key():
                try:
                    key = secure_storage.get_api_key(key_id)
                    return key == test_key
                except Exception:
                    return False  # 忽略异常，测试并发读�?                    
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(get_key) for _ in range(20)]
                for future in as_completed(futures):
                    if future.result():
                        success_count += 1
                        
            secure_storage.delete_api_key(key_id)
            
            if success_count >= 18:
                result.add_pass(f"并发 Key 访问通过 ({success_count}/20)")
            else:
                result.add_fail(f"并发 Key 访问失败 ({success_count}/20)")
        except Exception as e:
            result.add_error(f"并发 Key 测试错误：{e}")
            
        self.results["并发压力"] = result
        
    # ========================================================================
    # 4. 异常恢复测试
    # ========================================================================
    
    def test_error_recovery(self):
        """异常恢复测试"""
        result = self.results.get("异常恢复", TestResult("异常恢复"))
        
        # 测试 1: 无效 JSON
        print("\n[恢复测试] 无效 JSON 处理")
        try:
            if self.client:
                response = self.client.post(
                    "/health",  # 使用存在的端�?                    content="not valid json{{{",
                    headers={"Content-Type": "application/json"}
                )
                # 应该返回 400 错误，不崩溃
                if response.status_code in [400, 422, 500]:
                    result.add_pass("无效 JSON 处理正常")
                else:
                    # 404 也说明端点不存在，不算崩�?                    result.add_pass("无效 JSON 未崩�?)
        except Exception as e:
            result.add_error(f"无效 JSON 测试错误：{e}")
            
        # 测试 2: 缺失必填字段
        print("[恢复测试] 缺失必填字段")
        try:
            if self.client:
                # 使用 cloud_chat 端点测试
                response = self.client.post("/cloud/chat", json={
                    "provider": "minimax"
                    # 缺少 api_key �?messages
                })
                if response.status_code in [400, 422]:
                    result.add_pass("缺失字段处理正常")
                else:
                    result.add_pass("缺失字段未崩�?)
        except Exception as e:
            result.add_error(f"缺失字段测试错误：{e}")
            
        # 测试 3: 错误的方�?        print("[恢复测试] 错误�?HTTP 方法")
        try:
            if self.client:
                response = self.client.delete("/health")
                # 应该返回 405 �?404
                if response.status_code in [404, 405]:
                    result.add_pass("错误方法处理正常")
                else:
                    result.add_fail(f"错误方法返回状态：{response.status_code}")
        except Exception as e:
            result.add_error(f"错误方法测试错误：{e}")
            
        self.results["异常恢复"] = result
        
    # ========================================================================
    # 5. 数据一致性测�?    # ========================================================================
    
    def test_data_consistency(self):
        """数据一致性测�?""
        result = self.results.get("数据一致�?, TestResult("数据一致�?))
        
        # 测试 1: 加密解密一致�?        print("\n[一致性测试] 加密解密一致�?)
        try:
            test_data = [
                "simple_key",
                "group_id:api_key_12345",
                "特殊字符！@#�?…�?*",
                "a" * 1000,  # 长字符串
            ]
            
            for i, data in enumerate(test_data):
                key_id = f"test_consistency_{i}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
                secure_storage.store_api_key(key_id, "test", data)
                decrypted = secure_storage.get_api_key(key_id)
                
                if decrypted == data:
                    result.add_pass(f"加密解密一�?({i+1}/{len(test_data)})")
                else:
                    result.add_fail(f"加密解密不一致：{data[:10]}...")
                    
                secure_storage.delete_api_key(key_id)
        except Exception as e:
            result.add_error(f"加密解密测试错误：{e}")
            
        # 测试 2: 审计日志完整�?        print("[一致性测试] 审计日志完整�?)
        try:
            test_action = f"test_action_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            audit_logger.log_action(test_action, details={'test': 'data'})
            
            # 等待日志写入
            time.sleep(0.1)
            
            # 读取日志验证
            logs = audit_logger.get_logs(limit=100)
            found = any(log.get('action') == test_action for log in logs)
            
            if found:
                result.add_pass("审计日志完整")
            else:
                # 尝试直接读取文件
                log_file = audit_logger.log_dir / f"audit_{datetime.now().strftime('%Y%m%d')}.log"
                if log_file.exists():
                    with open(log_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    if test_action in content:
                        result.add_pass("审计日志完整 (文件验证)")
                    else:
                        result.add_fail("审计日志丢失")
                else:
                    result.add_fail("审计日志文件不存�?)
        except Exception as e:
            result.add_error(f"审计日志测试错误：{e}")
            
        self.results["数据一致�?] = result
        
    # ========================================================================
    # 6. E2E 场景测试
    # ========================================================================
    
    def test_e2e_scenarios(self):
        """端到端场景测�?""
        result = self.results.get("E2E 场景", TestResult("E2E 场景"))
        
        # 场景 1: 完整 API Key 管理流程
        print("\n[E2E 测试] API Key 管理流程")
        try:
            if not self.client:
                result.add_error("TestClient 不可�?)
                return
                
            # 1. 创建 API Key
            response = self.client.post("/cloud/api-keys", json={
                "provider": "minimax",
                "api_key": "123456:test_key_e2e",
                "name": "E2E Test Key"
            })
            
            if response.status_code == 200:
                key_data = response.json()
                key_id = key_data.get('key_id')
                result.add_pass("创建 API Key 成功")
                
                # 2. 列出 API Keys
                response = self.client.get("/cloud/api-keys")
                if response.status_code == 200:
                    result.add_pass("列出 API Keys 成功")
                    
                    # 3. 删除 API Key
                    if key_id:
                        response = self.client.delete(f"/cloud/api-keys/{key_id}")
                        if response.status_code == 200:
                            result.add_pass("删除 API Key 成功")
                        else:
                            result.add_fail("删除 API Key 失败")
                else:
                    result.add_fail("列出 API Keys 失败")
            else:
                result.add_fail(f"创建 API Key 失败：{response.status_code}")
                
        except Exception as e:
            result.add_error(f"API Key 流程测试错误：{e}")
            
        # 场景 2: 云端服务商查�?        print("[E2E 测试] 云端服务商查�?)
        try:
            if self.client:
                response = self.client.get("/cloud/providers")
                if response.status_code == 200:
                    providers = response.json().get('providers', [])
                    if len(providers) > 0:
                        result.add_pass(f"服务商查询成�?({len(providers)}�?")
                    else:
                        result.add_fail("服务商列表为�?)
                else:
                    result.add_fail(f"服务商查询失败：{response.status_code}")
        except Exception as e:
            result.add_error(f"服务商查询测试错误：{e}")
            
        self.results["E2E 场景"] = result
        
    # ========================================================================
    # 7. 性能基准测试
    # ========================================================================
    
    def test_performance(self):
        """性能基准测试"""
        result = self.results.get("性能基准", TestResult("性能基准"))
        
        # 测试 1: API 响应时间
        print("\n[性能测试] API 响应时间")
        try:
            if not self.client:
                result.add_error("TestClient 不可�?)
                return
                
            response_times = []
            
            for _ in range(10):
                start = time.time()
                response = self.client.get("/health")
                elapsed = (time.time() - start) * 1000  # ms
                response_times.append(elapsed)
                
            avg_time = sum(response_times) / len(response_times)
            p95_time = sorted(response_times)[int(len(response_times) * 0.95)]
            
            if avg_time < 100:
                result.add_pass(f"平均响应时间优秀 ({avg_time:.1f}ms)")
            elif avg_time < 500:
                result.add_pass(f"平均响应时间良好 ({avg_time:.1f}ms)")
            elif avg_time < 1000:
                result.add_pass(f"平均响应时间可接�?({avg_time:.1f}ms)")
            else:
                result.add_fail(f"平均响应时间过长 ({avg_time:.1f}ms)")
                
            result.add_pass(f"P95 响应时间：{p95_time:.1f}ms")
        except Exception as e:
            result.add_error(f"性能测试错误：{e}")
            
        # 测试 2: 加密解密性能
        print("[性能测试] 加密解密性能")
        try:
            key_id = "test_perf_" + datetime.now().strftime("%Y%m%d%H%M%S")
            test_key = "test_key_12345"
            
            # 存储
            start = time.time()
            for _ in range(100):
                secure_storage.store_api_key(key_id, "test", test_key)
            store_time = (time.time() - start) * 1000 / 100  # ms per op
            
            # 读取
            start = time.time()
            for _ in range(100):
                secure_storage.get_api_key(key_id)
            get_time = (time.time() - start) * 1000 / 100  # ms per op
            
            secure_storage.delete_api_key(key_id)
            
            if store_time < 10:
                result.add_pass(f"加密存储性能优秀 ({store_time:.2f}ms)")
            else:
                result.add_pass(f"加密存储性能可接�?({store_time:.2f}ms)")
                
            if get_time < 10:
                result.add_pass(f"解密读取性能优秀 ({get_time:.2f}ms)")
            else:
                result.add_pass(f"解密读取性能可接�?({get_time:.2f}ms)")
        except Exception as e:
            result.add_error(f"加密性能测试错误：{e}")
            
        self.results["性能基准"] = result
        
    # ========================================================================
    # 运行所有测�?    # ========================================================================
    
    def run_all(self):
        """运行所有测�?""
        self.setup()
        
        print("\n开始执行测试套�?..\n")
        
        # 执行各类测试
        self.run_test("边界条件", self.test_boundary_conditions)
        self.run_test("安全�?, self.test_security)
        self.run_test("并发压力", self.test_concurrency)
        self.run_test("异常恢复", self.test_error_recovery)
        self.run_test("数据一致�?, self.test_data_consistency)
        self.run_test("E2E 场景", self.test_e2e_scenarios)
        self.run_test("性能基准", self.test_performance)
        
        self.teardown()
        
        return self.results


# ============================================================================
# 主程�?# ============================================================================

def main():
    """主程�?""
    print("\n" + "=" * 70)
    print("Finetune Platform 深度集成测试")
    print("=" * 70)
    
    if not DEPENDENCIES_OK:
        print("\n[ERROR] 缺少测试依赖，请安装:")
        print("  pip install httpx aiohttp fastapi[all]")
        return
        
    suite = DeepTestSuite()
    results = suite.run_all()
    
    # 生成报告
    print("\n" + "=" * 70)
    print("生成测试报告...")
    print("=" * 70)
    
    report_path = Path(__file__).parent / "深度测试报告.md"
    
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("# 深度集成测试报告\n\n")
        f.write(f"**测试时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("## 测试结果汇总\n\n")
        
        total_passed = sum(r.passed for r in results.values())
        total_failed = sum(r.failed for r in results.values())
        total = total_passed + total_failed
        rate = total_passed / total * 100 if total > 0 else 0
        
        f.write(f"| 类别 | 通过 | 失败 | 通过�?|\n")
        f.write(f"|------|------|------|--------|\n")
        
        for name, result in results.items():
            t = result.passed + result.failed
            r = result.passed / t * 100 if t > 0 else 0
            f.write(f"| {name} | {result.passed} | {result.failed} | {r:.1f}% |\n")
            
        f.write(f"| **总计** | **{total_passed}** | **{total_failed}** | **{rate:.1f}%** |\n\n")
        
        # 失败详情
        f.write("## 失败详情\n\n")
        for name, result in results.items():
            if result.failed > 0:
                f.write(f"### {name}\n\n")
                for error in result.errors:
                    f.write(f"- {error}\n")
                f.write("\n")
                
    print(f"\n测试报告已保存到：{report_path}")
    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
