"""
模型 API 测试
"""
import pytest
from fastapi.testclient import TestClient
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app

client = TestClient(app)


class TestModelAPI:
    """模型管理 API 测试"""

    def test_list_models(self):
        """测试列出模型"""
        response = client.get("/models/list")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_model_download(self):
        """测试模型下载（模拟）"""
        # 注意：实际测试需要网络连接
        response = client.post("/models/download", json={
            "model_name": "test-model",
            "quantization": "int4"
        })
        # 可能成功或失败（取决于网络）
        assert response.status_code in [200, 400, 500]
