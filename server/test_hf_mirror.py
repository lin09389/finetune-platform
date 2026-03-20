"""测试 HuggingFace 镜像配置"""
import os
import sys

# 设置镜像
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'

print(f"HF_ENDPOINT: {os.environ.get('HF_ENDPOINT')}")
print("镜像配置成功!")

# 测试导入
try:
    from core.config import get_settings
    settings = get_settings()
    print(f"配置文件中的 HF_MIRROR: {settings.hf_mirror}")
except Exception as e:
    print(f"加载配置失败: {e}")

print("\n配置完成！现在可以正常下�?HuggingFace 模型了�?)
print("支持的镜像源�?)
print("  - hf-mirror: https://hf-mirror.com")
print("  - aliyun: https://mirrors.aliyun.com/huggingface")
print("  - modelscope: https://modelscope.cn/models")
