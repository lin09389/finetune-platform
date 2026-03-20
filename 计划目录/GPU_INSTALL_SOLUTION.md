# PyTorch GPU 安装方案（大文件下载超时解决）

## 问题
PyTorch CUDA 版本 2.7GB，网络下载超时

## 解决方案

### 方案 1：手动下载离线包（推荐）

1. **使用下载工具下载**（支持断点续传）

   复制链接到迅雷/IDM 等下载工具：
   ```
   https://download.pytorch.org/whl/cu118/torch-2.1.2%2Bcu118-cp311-cp311-win_amd64.whl
   https://download.pytorch.org/whl/cu118/torchvision-0.16.2%2Bcu118-cp311-cp311-win_amd64.whl
   https://download.pytorch.org/whl/cu118/torchaudio-2.1.2%2Bcu118-cp311-cp311-win_amd64.whl
   ```

2. **保存到本地目录**
   ```
   C:\Users\JHJ\Downloads\pytorch-gpu\
   ```

3. **离线安装**
   ```bash
   cd C:\Users\JHJ\Downloads\pytorch-gpu
   pip install torch-2.1.2+cu118-cp311-cp311-win_amd64.whl
   pip install torchvision-0.16.2+cu118-cp311-cp311-win_amd64.whl
   pip install torchaudio-2.1.2+cu118-cp311-cp311-win_amd64.whl
   ```

### 方案 2：使用 CPU 版本（临时）

当前已安装 CPU 版本，可以：
- ✅ 测试平台功能
- ✅ 开发调试
- ⚠️ 训练速度慢（无 GPU 加速）
- ⚠️ 无法进行大模型微调

### 方案 3：夜间下载

网络通常凌晨较快，可尝试：
```bash
pip install torch==2.1.2+cu118 torchvision==0.16.2+cu118 torchaudio==2.1.2+cu118 --index-url https://download.pytorch.org/whl/cu118
```

## 验证安装

```bash
python -c "import torch; print(torch.cuda.is_available())"
```

应输出：`True`

## 当前状态

```
✅ pip 镜像源：已配置（清华源）
✅ 显卡：RTX 3060 6GB
⚠️ PyTorch: CPU 版本 (2.1.2)
⏳ GPU 版本：等待下载
```
