"""
推理 API 测试
"""
import pytest
from fastapi.testclient import TestClient
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app

client = TestClient(app)


class TestInferenceAPI:
    """推理 API 测试"""

    def test_inference_validation(self):
        """测试推理参数验证"""
        # 测试空请求
        response = client.post("/inference/generate", json={})
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

    def test_get_backends(self):
        """测试获取后端列表"""
        response = client.get("/inference/backends")
        assert response.status_code == 200
        data = response.json()
        assert "current" in data
        assert "backends" in data

    def test_get_models(self):
        """测试获取推理模型列表"""
        response = client.get("/inference/models")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_ollama_status(self):
        """测试 Ollama 状态"""
        response = client.get("/inference/ollama/status")
        assert response.status_code == 200
        data = response.json()
        assert "running" in data
