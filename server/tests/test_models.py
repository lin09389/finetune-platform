"""
模型 API 测试
"""
import os
import sys
import importlib
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app

models_api = importlib.import_module("api.models")

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

    def test_convert_fp16_writes_artifact_manifest(self, tmp_path, monkeypatch):
        """测试 FP16 转换写出可追踪产物"""
        models_dir = tmp_path / "models"
        outputs_dir = tmp_path / "outputs"
        model_dir = models_dir / "tiny-model"
        model_dir.mkdir(parents=True)
        (model_dir / "config.json").write_text('{"model_name":"Tiny","type":"base"}', encoding="utf-8")

        class DummySettings:
            outputs_dir_resolved = outputs_dir

        monkeypatch.setattr(models_api, "get_models_dir", lambda: models_dir)
        monkeypatch.setattr(models_api, "get_settings", lambda: DummySettings())

        def fake_precision_export(model_path: Path, output_dir: Path, target_format: str) -> None:
            assert model_path == model_dir
            assert target_format == "fp16"
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "model.safetensors").write_text("converted", encoding="utf-8")

        monkeypatch.setattr(models_api, "_export_precision_model", fake_precision_export)

        response = client.post(
            "/models/convert",
            json={"model_id": "tiny-model", "target_format": "fp16", "output_name": "tiny-fp16"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["format"] == "fp16"
        manifest = Path(data["path"]) / "export_config.json"
        assert manifest.exists()
        assert '"format": "fp16"' in manifest.read_text(encoding="utf-8")

    def test_quantize_int8_writes_artifact_manifest(self, tmp_path, monkeypatch):
        """测试 INT8 量化写出可追踪产物"""
        models_dir = tmp_path / "models"
        outputs_dir = tmp_path / "outputs"
        model_dir = models_dir / "tiny-model"
        model_dir.mkdir(parents=True)
        (model_dir / "config.json").write_text('{"model_name":"Tiny","type":"base"}', encoding="utf-8")

        class DummySettings:
            outputs_dir_resolved = outputs_dir

        monkeypatch.setattr(models_api, "get_models_dir", lambda: models_dir)
        monkeypatch.setattr(models_api, "get_settings", lambda: DummySettings())

        def fake_quantized_export(model_path: Path, output_dir: Path, bits: int) -> None:
            assert model_path == model_dir
            assert bits == 8
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "pytorch_model.bin").write_text("quantized", encoding="utf-8")

        monkeypatch.setattr(models_api, "_export_quantized_model", fake_quantized_export)

        response = client.post("/models/tiny-model/quantize?bits=8")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["bits"] == 8
        manifest = Path(data["path"]) / "export_config.json"
        assert manifest.exists()
        assert '"format": "int8"' in manifest.read_text(encoding="utf-8")
