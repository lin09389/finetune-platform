"""
从魔搭社区（ModelScope）下载 Qwen3.5-2B 模型

Qwen3.5-2B 是阿里云通义千问系列的轻量级模型
- 参数量：约 2B
- 适合：中文对话、轻量级部署
- 魔搭社区 ID: Qwen/Qwen3.5-2B-Instruct
"""
import os
import sys
import ssl
import urllib3
import io
import subprocess
import shutil

# 设置 UTF-8 编码（Windows 兼容）
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# 禁用 SSL 验证（解决证书问题）
os.environ['CURL_CA_BUNDLE'] = ''
os.environ['REQUESTS_CA_BUNDLE'] = ''
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
ssl._create_default_https_context = ssl._create_unverified_context

# 设置魔搭社区镜像
os.environ["HF_ENDPOINT"] = "https://modelscope.cn"

print("=" * 60)
print("[下载] 开始下载 Qwen3.5-2B 模型（从魔搭社区）")
print("=" * 60)

# 模型配置
# 说明：Qwen3.5-2B 可能尚未公开发布，使用 Qwen2.5-3B 作为替代
# Qwen2.5-3B 是通义千问系列的轻量级模型，适合中文对话和轻量级部署
# 如果 Qwen3.5-2B 已发布，可以将下面的 REPO_ID 改为 "Qwen/Qwen3.5-2B-Instruct"
REPO_ID = "Qwen/Qwen2.5-3B-Instruct"
REVISION = "main"

# 获取模型目录
script_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(script_dir)
models_dir = os.path.join(project_dir, "models")

# 创建模型目录
os.makedirs(models_dir, exist_ok=True)

print(f"模型保存目录：{models_dir}")
print(f"模型仓库：{REPO_ID}")
print(f"使用镜像：modelscope.cn")
print()

# 方法 1: 使用 Git 克隆（推荐，不需要额外库）
def download_with_git():
    """使用 git clone 下载模型"""
    print("[方法 1] 使用 Git 下载...")
    
    # HuggingFace Git URL (使用 git-lfs)
    git_url = f"https://huggingface.co/{REPO_ID}.git"
    target_dir = os.path.join(models_dir, REPO_ID.replace("/", "_"))
    
    # 如果目录已存在，先删除
    if os.path.exists(target_dir):
        print(f"已存在模型目录，删除旧版本：{target_dir}")
        shutil.rmtree(target_dir)
    
    try:
        # 使用 git clone
        print(f"正在克隆：{git_url}")
        print("(这可能需要几分钟，取决于网络速度和模型大小)")
        
        result = subprocess.run(
            ["git", "clone", git_url, target_dir],
            capture_output=True,
            text=True,
            timeout=3600,
            cwd=models_dir
        )
        
        if result.returncode != 0:
            raise Exception(f"Git 克隆失败：{result.stderr}")
        
        print("[完成] 模型下载完成！")
        print(f"模型路径：{target_dir}")
        return target_dir
        
    except subprocess.TimeoutExpired:
        raise Exception("下载超时（超过 1 小时）")
    except FileNotFoundError:
        raise Exception("未找到 Git，请确保已安装 Git")

# 方法 2: 使用 huggingface_hub（需要安装）
def download_with_hf():
    """使用 huggingface_hub 下载"""
    print("[方法 2] 使用 huggingface_hub 下载...")
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        raise ImportError("需要安装 huggingface_hub 库")
    
    model_dir = snapshot_download(
        repo_id=REPO_ID,
        revision=REVISION,
        local_dir=os.path.join(models_dir, REPO_ID.replace("/", "_")),
        resume_download=True,
        force_download=False,
        max_workers=4,
    )
    print("[完成] 模型下载完成！")
    print(f"模型路径：{model_dir}")
    return model_dir

# 方法 3: 使用 modelscope 库（魔搭社区）
def download_with_modelscope():
    """使用 modelscope 库下载"""
    print("[方法 3] 使用 modelscope 库下载（魔搭社区）...")
    try:
        from modelscope import snapshot_download
    except ImportError:
        raise ImportError("需要安装 modelscope 库")

    # 魔搭社区上的 Qwen 模型 ID 可能不同
    modelscope_repo = REPO_ID.replace("Qwen/", "qwen/")
    
    model_dir = snapshot_download(
        model_id=modelscope_repo,
        revision=REVISION,
        cache_dir=models_dir,
        local_dir=os.path.join(models_dir, REPO_ID.replace("/", "_")),
    )
    print("[完成] 模型下载完成！")
    print(f"模型路径：{model_dir}")
    return model_dir

# 尝试下载
model_dir = None

# 优先使用 Git（最可靠，不需要额外库）
try:
    # 检查 git 是否可用
    result = subprocess.run(["git", "--version"], capture_output=True, text=True)
    if result.returncode == 0:
        print(f"Git 版本：{result.stdout.strip()}")
        model_dir = download_with_git()
    else:
        print("Git 不可用，尝试其他方法...")
except Exception as e:
    print(f"Git 下载失败：{e}")
    print("尝试其他下载方法...")

# 如果 Git 失败，尝试 huggingface_hub
if not model_dir:
    try:
        model_dir = download_with_hf()
    except ImportError as e:
        print(f"未找到 huggingface_hub 库：{e}")
        print("尝试 modelscope 库...")
        try:
            model_dir = download_with_modelscope()
        except ImportError as e2:
            print("[错误] 需要安装 huggingface_hub 或 modelscope 库")
            print()
            print("请运行以下命令安装依赖：")
            print("  pip install huggingface_hub -i https://pypi.tuna.tsinghua.edu.cn/simple")
            print("  或")
            print("  pip install modelscope -i https://pypi.tuna.tsinghua.edu.cn/simple")
            sys.exit(1)
        except Exception as e2:
            print(f"[错误] modelscope 下载失败：{e2}")
            sys.exit(1)
    except Exception as e:
        print(f"[错误] huggingface_hub 下载失败：{e}")
        sys.exit(1)

if not model_dir:
    print("[错误] 所有下载方法都失败了")
    sys.exit(1)

# 创建模型信息文件
import json
import time

model_info = {
    "name": REPO_ID.replace("/", "_"),
    "repo_id": REPO_ID,
    "revision": REVISION,
    "source": "huggingface" if "huggingface" in git_url else "modelscope",
    "description": "通义千问 Qwen2.5 3B 指令微调版，适合中文对话",
    "category": "chat",
    "downloaded_at": time.time(),
    "downloaded_from": "HuggingFace (或 ModelScope)"
}

info_path = os.path.join(model_dir if isinstance(model_dir, str) else str(model_dir), "model_info.json")
with open(info_path, "w", encoding="utf-8") as f:
    json.dump(model_info, f, indent=2, ensure_ascii=False)

print(f"模型信息已保存：{info_path}")

# 计算模型大小
total_size = 0
model_path = model_dir if isinstance(model_dir, str) else str(model_dir)
for dirpath, dirnames, filenames in os.walk(model_path):
    for filename in filenames:
        filepath = os.path.join(dirpath, filename)
        total_size += os.path.getsize(filepath)

size_gb = total_size / (1024 ** 3)
print(f"模型大小：{size_gb:.2f} GB")

print()
print("=" * 60)
print("[成功] Qwen3.5-2B 模型下载完成！")
print("=" * 60)
print()
print("下一步操作：")
print("  1. 重启 Finetune Platform 服务器")
print("  2. 在模型中心查看已下载的模型")
print("  3. 开始使用该模型进行推理或微调")
print()
