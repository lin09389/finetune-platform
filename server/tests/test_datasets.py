"""
数据集 API 测试
"""
import pytest
from fastapi.testclient import TestClient
import sys
import os
import json
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app

client = TestClient(app)


class TestDatasetAPI:
    """数据集 API 测试"""

    def test_list_datasets(self):
        """测试列出数据集"""
        response = client.get("/datasets/list")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_upload_validation(self):
        """测试上传参数验证"""
        # 测试空请求
        response = client.post("/datasets/upload")
        assert response.status_code == 422

    def test_get_statistics_not_found(self):
        """测试获取不存在的数据集统计"""
        response = client.get("/datasets/nonexistent/statistics")
        assert response.status_code == 404

    def test_delete_not_found(self):
        """测试删除不存在的数据集"""
        response = client.delete("/datasets/nonexistent")
        assert response.status_code == 404
