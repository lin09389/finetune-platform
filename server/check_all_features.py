# -*- coding: utf-8 -*-
"""
项目功能全面检测脚�?"""
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 60)
print("Finetune Platform 功能全面检�?)
print("=" * 60)

results = {"passed": [], "warnings": [], "errors": []}

def check_module(name, import_path=None):
    try:
        if import_path:
            __import__(import_path)
        else:
            __import__(name)
        results["passed"].append(f"[OK] {name}")
        return True
    except ImportError as e:
        results["errors"].append(f"[ERROR] {name}: {str(e)}")
        return False
    except Exception as e:
        results["warnings"].append(f"[WARN] {name}: {str(e)}")
        return False

def check_file(path, name):
    if Path(path).exists():
        results["passed"].append(f"[FILE] {name}")
        return True
    else:
        results["errors"].append(f"[ERROR] {name} 不存�?)
        return False

def check_dir(path, name):
    if Path(path).exists() and Path(path).is_dir():
        results["passed"].append(f"[DIR] {name}")
        return True
    else:
        results["errors"].append(f"[ERROR] {name} 不存�?)
        return False

# 1. PyTorch 检�?print("\n[1] PyTorch 环境检�?)
print("-" * 40)
try:
    import torch
    print(f"PyTorch: {torch.__version__}")
    print(f"CUDA 可用：{torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"GPU: {torch.cuda.get_device_name(0)}")
except Exception as e:
    print(f"Error: {e}")

# 2. 核心依赖检�?print("\n[2] 核心依赖检�?)
print("-" * 40)
for name, module in [("FastAPI", "fastapi"), ("Uvicorn", "uvicorn"), ("Pydantic", "pydantic"), 
                     ("Transformers", "transformers"), ("Accelerate", "accelerate"), 
                     ("PEFT", "peft"), ("Datasets", "datasets")]:
    check_module(name, module)

# 3. API 模块检�?print("\n[3] API 模块检�?)
print("-" * 40)
api_modules = ["api.device", "api.models", "api.datasets", "api.training", 
               "api.inference", "api.chat_history", "api.rag", "api.workspace", 
               "api.model_center", "api.memory", "api.agent", "api.context"]
for module in api_modules:
    check_module(module)

# 4. Context 模块检�?print("\n[4] 项目上下文模块检�?)
print("-" * 40)
context_modules = ["context", "context.models", "context.project_scanner", 
                   "context.symbol_extractor", "context.code_indexer", 
                   "context.context_retriever", "context.service"]
for module in context_modules:
    check_module(module)

# 5. RAG 模块检�?print("\n[5] RAG 模块检�?)
print("-" * 40)
rag_modules = ["rag", "rag.embedder", "rag.vector_store", "rag.service", 
               "rag.document_parser", "rag.text_chunker"]
for module in rag_modules:
    check_module(module)

# 6. Agent 模块检�?print("\n[6] Agent 模块检�?)
print("-" * 40)
agent_modules = ["agent", "agent.config", "agent.security", "agent.executor", 
                 "agent.intent", "agent.audit"]
for module in agent_modules:
    check_module(module)

# 7. Core 模块检�?print("\n[7] Core 模块检�?)
print("-" * 40)
core_modules = ["core.config", "core.logging", "core.utils", "core.model_cache", 
                "core.training_queue", "core.training_state", "core.db_manager"]
for module in core_modules:
    check_module(module)

# 8. 目录检�?print("\n[8] 目录结构检�?)
print("-" * 40)
server_path = Path(__file__).parent
for d in ["models", "datasets", "outputs", "data", "logs"]:
    check_dir(server_path / d, d)

# 9. 前端检�?print("\n[9] 前端检�?)
print("-" * 40)
client_path = server_path.parent / "client"
for f in ["package.json", "vite.config.ts", "tsconfig.json"]:
    check_file(client_path / f, f)

for comp in ["App.tsx", "main.tsx", "pages/Chat.tsx", "pages/Training.tsx", 
             "pages/ProjectContext.tsx", "components/CodePreview.tsx"]:
    check_file(client_path / "src" / comp, comp)

# 打印汇�?print("\n" + "=" * 60)
print("检测结果汇�?)
print("=" * 60)
print(f"[OK] 通过：{len(results['passed'])}")
print(f"[WARN] 警告：{len(results['warnings'])}")
print(f"[ERROR] 错误：{len(results['errors'])}")

if results["warnings"]:
    print("\n警告详情:")
    for w in results["warnings"]:
        print(f"  {w}")

if results["errors"]:
    print("\n错误详情:")
    for e in results["errors"]:
        print(f"  {e}")

# API 端点测试
print("\n" + "=" * 60)
print("API 端点测试")
print("=" * 60)

try:
    from fastapi.testclient import TestClient
    from main import app
    
    client = TestClient(app)
    
    endpoints = [
        ("/health", True),
        ("/", True),
        ("/api/info", True),
        ("/device/info", False),
        ("/context/projects", False),
        ("/models/list", False),
        ("/datasets/list", False),
    ]
    for ep, should_work in endpoints:
        try:
            response = client.get(ep)
            if response.status_code == 200:
                print(f"[OK] {ep}")
            elif response.status_code == 404:
                print(f"[WARN] {ep} - 404 (可能路径变更)")
            else:
                print(f"[ERROR] {ep} - Status: {response.status_code}")
        except Exception as e:
            print(f"[ERROR] {ep} - {e}")
            
except ImportError as e:
    print(f"[WARN] 无法导入测试客户端：{e}")
    print("  请安装：pip install httpx")
except Exception as e:
    print(f"[ERROR] 服务器测试失败：{e}")

print("\n" + "=" * 60)
print("检测完�?")
print("=" * 60)
