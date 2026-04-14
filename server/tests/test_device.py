"""
设备 API 测试
"""
import os
import sys

from fastapi.testclient import TestClient

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
        """测试健康检查"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "timestamp" in data
        assert "cuda_available" in data

    def test_root_endpoint(self):
        """测试根端点"""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "1.0.0"

    def test_api_info_uses_canonical_routes_and_tiers(self):
        """测试 API 元数据使用真实的规范路由和能力分层"""
        response = client.get("/api/info")
        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "2.1.0"
        assert data["endpoints"]["chat"] == "/chat/sessions"
        assert data["endpoints"]["knowledge"] == "/knowledge"
        assert data["endpoints"]["memory"] == "/memory"
        assert "capability_tiers" in data
        assert "experimental" in data["capability_tiers"]
