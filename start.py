#!/usr/bin/env python
"""直接启动测试"""
import sys
import os

if not os.environ.get("SystemRoot"):
    os.environ["SystemRoot"] = r"C:\Windows"
if not os.environ.get("WINDIR"):
    os.environ["WINDIR"] = r"C:\Windows"
if not os.environ.get("SystemDrive"):
    os.environ["SystemDrive"] = "C:"

# 添加服务器路径
server_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'server')
sys.path.insert(0, server_path)
os.chdir(server_path)

print(f"工作目录：{os.getcwd()}")
print(f"Python 版本：{sys.version}")
print(f"路径：{sys.path[:3]}")

# 导入应用
print("\n导入应用...")
from main import app
print(f"应用：{app}")

# 启动服务器
print("\n启动服务器...")
import uvicorn
print("服务器将在 http://127.0.0.1:8000 启动")
uvicorn.run(app, host="127.0.0.1", port=8000)
