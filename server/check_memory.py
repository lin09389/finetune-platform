import os
import sys

server_dir = r'c:\Users\JHJ\Desktop\finetune-platform\server'
sys.path.insert(0, server_dir)

files_to_check = [
    'memory/memory_service.py',
    'memory/memory_extractor.py',
    'memory/models.py',
    'memory/knowledge_graph.py',
    'memory/short_term_memory.py',
    'memory/intelligent_extractor.py',
    'memory/memory_merger.py',
    'memory/enhanced_memory_service.py',
    'memory/mcp_server.py',
    'memory/operation_memory.py',
    'memory/preference_learner.py',
]

for f in files_to_check:
    path = os.path.join(server_dir, f)
    if os.path.exists(path):
        try:
            with open(path, encoding='utf-8') as file:
                content = file.read()
            print(f"OK: {f}")
        except UnicodeDecodeError as e:
            print(f"FAIL: {f} - {e}")
        except Exception as e:
            print(f"ERROR: {f} - {e}")
    else:
        print(f"NOT FOUND: {f}")
