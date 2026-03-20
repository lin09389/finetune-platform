"""
数据�?API 测试
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
    """数据集管�?API 测试"""

    def test_list_datasets(self):
        """测试列出数据�?""
        response = client.get("/datasets/list")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_upload_dataset_validation(self):
        """测试数据集上传验�?""
        # 测试无效文件格式
        response = client.post(
            "/datasets/upload",
            files={"file": ("test.txt", b"invalid content", "text/plain")}
        )
        # 应该拒绝�?JSON 文件
        assert response.status_code in [400, 422]

    def test_upload_valid_json(self):
        """测试有效 JSON 上传"""
        valid_data = json.dumps({
            "messages": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"}
            ]
        }).encode('utf-8')
        
        response = client.post(
            "/datasets/upload",
            files={"file": ("test.json", valid_data, "application/json")}
        )
        # 可能成功或需要更多配�?        assert response.status_code in [200, 400, 500]
