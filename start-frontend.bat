@echo off
chcp 65001 >nul
echo 启动前端服务...
cd /d %~dp0client
npm run dev
pause
