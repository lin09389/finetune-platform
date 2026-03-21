"""
训练 API 测试
"""
import pytest
from fastapi.testclient import TestClient
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app

client = TestClient(app)


class TestTrainingAPI:
    """训练 API 测试"""

    def test_get_progress_idle(self):
        """测试获取训练进度（空闲状态）"""
        response = client.get("/training/progress")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] in ["idle", "running", "completed", "failed", "stopped"]

    def test_get_history(self):
        """测试获取训练历史"""
        response = client.get("/training/history")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_status(self):
        """测试获取训练状态"""
        response = client.get("/training/status")
        assert response.status_code == 200
        data = response.json()
        assert "is_training" in data

    def test_start_training_validation(self):
        """测试开始训练参数验证"""
        # 测试缺失参数
        response = client.post("/training/start", json={})
        assert response.status_code == 422

        # 测试无效模型 ID
        response = client.post("/training/start", json={
            "model_id": "nonexistent",
            "dataset_id": "nonexistent",
            "method": "qlora"
        })
        assert response.status_code in [400, 404]

    def test_stop_training_when_idle(self):
        """测试停止训练（空闲状态）"""
        response = client.post("/training/stop")
        # 空闲时应该返回错误
        assert response.status_code == 400
