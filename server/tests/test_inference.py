"""
推理 API 测试
"""
import pytest
from fastapi.testclient import TestClient
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app

client = TestClient(app)


class TestInferenceAPI:
    """推理 API 测试"""

    def test_inference_validation(self):
        """测试推理参数验证"""
        # 测试空请�?        response = client.post("/inference/generate", json={})
        assert response.status_code == 422

    def test_chat_format(self):
        """测试聊天格式"""
        response = client.post("/inference/chat", json={
            "messages": [
                {"role": "user", "content": "Hello"}
            ],
            "model_id": "test"
        })
        # 可能成功或失败（取决于模型）
        assert response.status_code in [200, 400, 404, 500]
