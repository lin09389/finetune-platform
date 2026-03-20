"""
设备 API 测试
"""
import pytest
from fastapi.testclient import TestClient
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app

client = TestClient(app)


class TestDeviceAPI:
    """设备相关 API 测试"""

    def test_get_device_info(self):
        """测试获取设备信息"""
        response = client.get("/device/info")
        assert response.status_code == 200
        data = response.json()
        assert "cuda_available" in data
        assert "device_name" in data
        assert "memory" in data

    def test_health_check(self):
        """测试健康检�?""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "timestamp" in data
        assert "cuda_available" in data

    def test_root_endpoint(self):
        """测试根端�?""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "1.0.0"
