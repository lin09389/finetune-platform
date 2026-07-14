@echo off
chcp 65001 >nul
setlocal
title PyTorch GPU 安装器（转发）

rem 根目录转发脚本：实际实现位于 server\install-gpu.bat
rem 保留此文件以兼容 README.md / README_EN.md 中的历史命令 install-pytorch-gpu.bat

call "%~dp0server\install-gpu.bat" %*
exit /b %errorlevel%
