# -*- coding: utf-8 -*-
"""测试所有修复后的模块导入"""
import sys
import os

# 设置路径
server_path = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, server_path)

results = {"passed": [], "failed": []}

def test_import(module_path, class_name=None):
    """测试模块导入"""
    try:
        parts = module_path.split('.')
        module = __import__(module_path)
        for part in parts[1:]:
            module = getattr(module, part)
        
        if class_name:
            getattr(module, class_name)
        
        results["passed"].append(module_path)
        print(f"  [OK] {module_path}")
        return True
    except Exception as e:
        results["failed"].append((module_path, str(e)))
        print(f"  [FAIL] {module_path}: {e}")
        return False

print("=" * 60)
print("测试 skills 模块")
print("=" * 60)

test_import("skills.registry", "SkillRegistry")
test_import("skills.base", "SkillBase")
test_import("skills.models", "SkillStatus")
test_import("skills.scanner", "SkillScanner")
test_import("skills.enhanced_registry", "EnhancedSkillRegistry")
test_import("skills.lifecycle", "SkillLifecycleManager")
test_import("skills.cache", "SkillExecutionCache")
test_import("skills.sandbox", "SkillSandbox")
test_import("skills.executor", "SkillExecutor")
test_import("skills.decision_engine", "DecisionEngine")
test_import("skills.param_extractor", "ParamExtractor")
test_import("skills.result_processor", "ResultProcessor")

print()
print("=" * 60)
print("测试 security 模块")
print("=" * 60)

test_import("security.encryption", "SecureStorage")
test_import("security.file_sandbox")
test_import("security.data_masking", "DataMasker")
test_import("security.middleware", "SecurityMiddleware")
test_import("security.rate_limiter", "RateLimiter")
test_import("security.jwt_auth", "JWTAuth")
test_import("security.auth_middleware", "SecurityMiddleware")

print()
print("=" * 60)
print("测试 api 模块")
print("=" * 60)

test_import("api.errors", "APIError")
test_import("api.ocr")
test_import("api.skills")
test_import("api.inference.routes")

print()
print("=" * 60)
print("测试 core 模块")
print("=" * 60)

test_import("core.file_parser", "FileParser")

print()
print("=" * 60)
print("测试 cua 模块")
print("=" * 60)

test_import("cua.exceptions", "CUAError")

print()
print("=" * 60)
print("测试 rag 模块")
print("=" * 60)

test_import("rag.embedder", "get_embedder")
test_import("rag.vector_store", "get_vector_store")
test_import("rag.document_parser", "DocumentParser")
test_import("rag.text_chunker", "TextChunker")
test_import("rag.service", "RAGService")

print()
print("=" * 60)
print("测试 context 模块")
print("=" * 60)

test_import("context.service", "ContextService")
test_import("context.models", "ContextInfo")
test_import("context.project_scanner", "ProjectScanner")
test_import("context.context_retriever", "ContextRetriever")

print()
print("=" * 60)
print("测试 memory 模块")
print("=" * 60)

test_import("memory.operation_memory", "OperationMemoryManager")
test_import("memory.preference_learner", "UserPreferenceLearner")

print()
print("=" * 60)
print("测试结果汇总")
print("=" * 60)

print(f"通过: {len(results['passed'])}")
print(f"失败: {len(results['failed'])}")

if results["failed"]:
    print()
    print("失败的模块:")
    for module_path, error in results["failed"]:
        print(f"  - {module_path}: {error[:100]}")

print()
print("测试完成!")
