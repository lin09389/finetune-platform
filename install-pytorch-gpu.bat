@echo off
chcp 65001 >nul
title PyTorch GPU 安装器

echo ========================================
echo   PyTorch GPU 版本安装
echo ========================================
echo.
echo 检测到：NVIDIA GeForce RTX 3060 6GB
echo 目标版本：PyTorch 2.1.2 + CUDA 11.8
echo.

REM 尝试多个镜像源
set MIRRORS=^
https://pypi.tuna.tsinghua.edu.cn/simple ^
https://mirrors.aliyun.com/pypi/simple/ ^
https://pypi.mirrors.ustc.edu.cn/simple/

echo [1/4] 卸载当前 PyTorch...
pip uninstall -y torch torchvision torchaudio -q

echo [2/4] 尝试镜像源安装...
echo.

REM 尝试清华源
echo 尝试清华源...
pip install torch==2.1.2 torchvision torchaudio --index-url https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn -q
if not errorlevel 1 goto :success

REM 尝试阿里源
echo 清华源失败，尝试阿里源...
pip install torch==2.1.2 torchvision torchaudio --index-url https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com -q
if not errorlevel 1 goto :success

REM 尝试中科大源
echo 阿里源失败，尝试中科大源...
pip install torch==2.1.2 torchvision torchaudio --index-url https://pypi.mirrors.ustc.edu.cn/simple/ -q
if not errorlevel 1 goto :success

echo.
echo [错误] 所有镜像源安装失败！
echo 建议：检查网络连接或使用手机热点
goto :end

:success
echo.
echo [OK] PyTorch 安装成功

echo.
echo [3/4] 安装 bitsandbytes (可选，用于 4bit 量化)...
pip install bitsandbytes==0.41.3 -q

echo.
echo [4/4] 验证安装...
python -c "import torch; print('PyTorch:', torch.__version__); print('CUDA 可用:', torch.cuda.is_available()); print('CUDA 版本:', torch.version.cuda if hasattr(torch.version, 'cuda') else 'N/A'); print('GPU 名称:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'N/A')"

:end
echo.
echo ========================================
pause
