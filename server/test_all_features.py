# -*- coding: utf-8 -*-
"""
项目功能全面测试脚本
测试所有模块、API 端点、安全功�?"""
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 70)
print("Finetune Platform 全面功能测试")
print("=" * 70)

results = {"passed": [], "warnings": [], "errors": []}

def test_module(name, import_path=None):
    """测试模块导入"""
    try:
        if import_path:
            __import__(import_path)
        else:
            __import__(name)
        results["passed"].append(f"[OK] {name}")
        print(f"  [OK] {name}")
        return True
    except ImportError as e:
        results["errors"].append(f"[ERROR] {name}: {str(e)}")
        print(f"  [ERROR] {name}: {str(e)}")
        return False
    except Exception as e:
        results["warnings"].append(f"[WARN] {name}: {str(e)}")
        print(f"  [WARN] {name}: {str(e)}")
        return False

def test_function(desc, func):
    """测试函数执行"""
    try:
        func()
        results["passed"].append(f"[OK] {desc}")
        print(f"  [OK] {desc}")
        return True
    except Exception as e:
        results["errors"].append(f"[ERROR] {desc}: {str(e)}")
        print(f"  [ERROR] {desc}: {str(e)}")
        return False

# 1. PyTorch 环境检�?print("\n[1] PyTorch 环境检�?)
print("-" * 50)
try:
    import torch
    print(f"  PyTorch: {torch.__version__}")
    print(f"  CUDA 可用：{torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"  GPU: {torch.cuda.get_device_name(0)}")
    else:
        print(f"  [WARN] CPU 版本（无 GPU 加速）")
except Exception as e:
    print(f"  [ERROR] PyTorch 错误：{e}")

# 2. 核心依赖测试
print("\n[2] 核心依赖测试")
print("-" * 50)
core_deps = [
    ("FastAPI", "fastapi"),
    ("Uvicorn", "uvicorn"),
    ("Pydantic", "pydantic"),
    ("Transformers", "transformers"),
    ("Accelerate", "accelerate"),
    ("PEFT", "peft"),
    ("Datasets", "datasets"),
    ("Httpx", "httpx"),
    ("Cryptography", "cryptography"),
]
for name, module in core_deps:
    test_module(name, module)

# 3. 后端 API 模块测试
print("\n[3] 后端 API 模块测试")
print("-" * 50)
api_modules = [
    "api.device",
    "api.models",
    "api.datasets",
    "api.training",
    "api.inference",
    "api.chat_history",
    "api.rag",
    "api.workspace",
    "api.model_center",
    "api.memory",
    "api.agent",
    "api.context",
    "api.cloud_chat",
]
for module in api_modules:
    test_module(module)

# 4. 安全模块测试
print("\n[4] 安全模块测试")
print("-" * 50)
test_module("security")
test_module("security.encryption")
test_module("security.file_sandbox")
test_module("security.audit_log")

# 5. Context 模块测试
print("\n[5] 项目上下文模块测�?)
print("-" * 50)
context_modules = [
    "context",
    "context.models",
    "context.project_scanner",
    "context.symbol_extractor",
    "context.code_indexer",
    "context.context_retriever",
    "context.service",
]
for module in context_modules:
    test_module(module)

# 6. RAG 模块测试
print("\n[6] RAG 模块测试")
print("-" * 50)
rag_modules = [
    "rag",
    "rag.embedder",
    "rag.vector_store",
    "rag.service",
    "rag.document_parser",
    "rag.text_chunker",
]
for module in rag_modules:
    test_module(module)

# 7. Agent 模块测试
print("\n[7] Agent 模块测试")
print("-" * 50)
agent_modules = [
    "agent",
    "agent.config",
    "agent.security",
    "agent.executor",
    "agent.intent",
    "agent.audit",
]
for module in agent_modules:
    test_module(module)

# 8. Core 模块测试
print("\n[8] Core 模块测试")
print("-" * 50)
core_modules = [
    "core.config",
    "core.logging",
    "core.utils",
    "core.model_cache",
    "core.training_queue",
    "core.training_state",
    "core.db_manager",
]
for module in core_modules:
    test_module(module)

# 9. AI 网关测试
print("\n[9] AI 网关测试")
print("-" * 50)
test_module("ai")
test_module("ai.gateway")

# 10. 功能测试
print("\n[10] 功能测试")
print("-" * 50)

def test_encryption():
    """测试加密解密"""
    from security.encryption import secure_storage
    # 测试加密
    test_key = "test_12345:abcdef"
    secure_storage.store_api_key("_test_func", "minimax", test_key)
    # 测试解密
    decrypted = secure_storage.get_api_key("_test_func")
    assert decrypted == test_key, f"解密失败：{decrypted} != {test_key}"
    # 清理
    secure_storage.delete_api_key("_test_func")

test_function("加密解密测试", test_encryption)

def test_file_sandbox():
    """测试文件沙箱"""
    from security.file_sandbox import file_sandbox
    
    # 测试获取沙箱信息
    info = file_sandbox.get_sandbox_info()
    assert 'working_dir' in info
    assert 'allowed_operations' in info
    
    # 测试列出文件
    files = file_sandbox.list_files(".", "*.py")
    assert isinstance(files, list)

test_function("文件沙箱测试", test_file_sandbox)

def test_audit_logger():
    """测试审计日志"""
    from security.audit_log import audit_logger
    
    # 测试记录日志
    audit_logger.log_action('test_action', details={'test': 'data'})
    
    # 测试获取统计
    stats = audit_logger.get_stats()
    assert 'total_actions' in stats

test_function("审计日志测试", test_audit_logger)

def test_providers():
    """测试服务商列�?""
    from ai.gateway import list_providers
    providers = list_providers()
    assert len(providers) > 0
    assert any(p['id'] == 'minimax' for p in providers)

test_function("服务商列表测�?, test_providers)

def test_context_scanner():
    """测试项目扫描�?""
    from context.project_scanner import ProjectScanner
    
    # 测试扫描当前项目
    scanner = ProjectScanner(str(Path(__file__).parent))
    info = scanner.scan()
    assert info.name
    assert info.tech_stack

test_function("项目扫描器测�?, test_context_scanner)

# 11. API 端点测试
print("\n[11] API 端点测试")
print("-" * 50)

try:
    from fastapi.testclient import TestClient
    from main import app
    
    client = TestClient(app)
    
    endpoints = [
        ("/health", 200, "健康检�?),
        ("/", 200, "根路�?),
        ("/api/info", 200, "API 信息"),
        ("/device/info", 200, "设备信息"),
        ("/context/projects", 200, "项目列表"),
        ("/cloud/providers", 200, "云端服务�?),
        ("/cloud/api-keys", 200, "API Keys 列表"),
    ]
    
    for endpoint, expected_status, desc in endpoints:
        try:
            response = client.get(endpoint)
            if response.status_code == expected_status:
                print(f"  [OK] {desc} ({endpoint})")
                results["passed"].append(f"[OK] {desc}")
            else:
                print(f"  [WARN] {desc} ({endpoint}) - Status: {response.status_code}")
                results["warnings"].append(f"[WARN] {desc}: {response.status_code}")
        except Exception as e:
            print(f"  [ERROR] {desc} ({endpoint}) - {e}")
            results["errors"].append(f"[ERROR] {desc}: {str(e)}")
            
except ImportError as e:
    print(f"  [WARN] 无法导入测试客户端：{e}")
except Exception as e:
    print(f"  [ERROR] API 测试失败：{e}")
    results["errors"].append(f"[ERROR] API 测试：{str(e)}")

# 12. 目录结构检�?print("\n[12] 目录结构检�?)
print("-" * 50)

server_path = Path(__file__).parent
required_dirs = ["models", "datasets", "outputs", "data", "logs"]
for d in required_dirs:
    dir_path = server_path / d
    if dir_path.exists() and dir_path.is_dir():
        print(f"  [OK] {d}/")
        results["passed"].append(f"[OK] 目录：{d}")
    else:
        print(f"  [ERROR] {d}/ (不存�?")
        results["errors"].append(f"[ERROR] 目录不存在：{d}")

# 13. 关键文件检�?print("\n[13] 关键文件检�?)
print("-" * 50)

required_files = [
    "main.py",
    "requirements.txt",
    ".env.example",
]
for f in required_files:
    file_path = server_path / f
    if file_path.exists():
        print(f"  [OK] {f}")
        results["passed"].append(f"[OK] 文件：{f}")
    else:
        print(f"  [ERROR] {f} (不存�?")
        results["errors"].append(f"[ERROR] 文件不存在：{f}")

# 安全模块文件
security_files = [
    "security/encryption.py",
    "security/file_sandbox.py",
    "security/audit_log.py",
]
for f in security_files:
    file_path = server_path / f
    if file_path.exists():
        print(f"  [OK] {f}")
        results["passed"].append(f"[OK] 安全文件：{f}")
    else:
        print(f"  [ERROR] {f} (不存�?")
        results["errors"].append(f"[ERROR] 安全文件不存在：{f}")

# 打印汇�?print("\n" + "=" * 70)
print("测试结果汇�?)
print("=" * 70)

print(f"\n通过：{len(results['passed'])}")
print(f"警告：{len(results['warnings'])}")
print(f"错误：{len(results['errors'])}")

if results["warnings"]:
    print("\n警告详情:")
    for w in results["warnings"]:
        print(f"  {w}")

if results["errors"]:
    print("\n错误详情:")
    for e in results["errors"]:
        print(f"  {e}")

# 总体评价
print("\n" + "=" * 70)
print("总体评价")
print("=" * 70)

total_tests = len(results['passed']) + len(results['warnings']) + len(results['errors'])
pass_rate = len(results['passed']) / total_tests * 100 if total_tests > 0 else 0

print(f"\n总测试数：{total_tests}")
print(f"通过率：{pass_rate:.1f}%")

if len(results['errors']) == 0:
    print("\n[OK] 所有测试通过！项目功能正常！")
elif len(results['errors']) <= 3:
    print("\n[WARN] 大部分功能正常，有少量错误需要修�?)
else:
    print("\n[ERROR] 存在多个错误，需要检查修�?)

print("\n" + "=" * 70)
print("测试完成!")
print("=" * 70)
