@echo off
chcp 65001 >nul
echo ========================================
echo   安装 GPU 版 PyTorch
echo ========================================
echo.
echo 显卡：NVIDIA GeForce RTX 3060 6GB
echo CUDA: 13.1 (驱动支持)
echo 目标：PyTorch 2.1.2 + CUDA 11.8
echo.
echo 正在安装 GPU 版 PyTorch...
echo.

REM 卸载当前 CPU 版本
echo [1/3] 卸载当前 PyTorch...
pip uninstall -y torch torchvision torchaudio

REM 安装 CUDA 11.8 版本（最稳定兼容）
echo [2/3] 安装 GPU 版 PyTorch (CUDA 11.8)...
pip install torch==2.1.2 torchvision torchaudio --index-url https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn

if errorlevel 1 (
    echo.
    echo [错误] 安装失败，尝试备用镜像源...
    pip install torch==2.1.2 torchvision torchaudio --index-url https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com
)

echo.
echo [3/3] 验证安装...
python -c "import torch; print('PyTorch:', torch.__version__); print('CUDA:', torch.cuda.is_available()); print('CUDA Version:', torch.version.cuda if hasattr(torch.version, 'cuda') else 'N/A')"

echo.
echo ========================================
echo   安装完成
echo ========================================
pause
