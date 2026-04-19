@echo off
chcp 65001 >nul
if not defined SystemRoot set "SystemRoot=C:\Windows"
if not defined WINDIR set "WINDIR=C:\Windows"
if not defined SystemDrive set "SystemDrive=C:"
echo 启动后端服务...
cd /d %~dp0server
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --log-level debug
pause
