"""
模型 API 测试
"""
import importlib
import json
import os
import sys
import types
from pathlib import Path
from types import SimpleNamespace

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

    def test_merge_lora_with_explicit_adapter_path_writes_manifest(self, tmp_path, monkeypatch):
        """测试 LoRA 合并导出接口会写出 manifest"""
        models_dir = tmp_path / "models"
        outputs_dir = tmp_path / "outputs"
        model_dir = models_dir / "tiny-model"
        adapter_dir = tmp_path / "training" / "lora_adapter"
        model_dir.mkdir(parents=True)
        adapter_dir.mkdir(parents=True)
        (model_dir / "config.json").write_text('{"model_name":"Tiny","type":"base"}', encoding="utf-8")
        (adapter_dir / "adapter_config.json").write_text("{}", encoding="utf-8")

        class DummySettings:
            outputs_dir_resolved = outputs_dir

        fake_transformers = types.ModuleType("transformers")

        class DummyTokenizer:
            @classmethod
            def from_pretrained(cls, model_path, trust_remote_code=True):
                assert Path(model_path) == model_dir
                return cls()

            def save_pretrained(self, output_dir):
                Path(output_dir).mkdir(parents=True, exist_ok=True)
                (Path(output_dir) / "tokenizer.json").write_text("tokenizer", encoding="utf-8")

        class DummyModel:
            def save_pretrained(self, output_dir, safe_serialization=True):
                Path(output_dir).mkdir(parents=True, exist_ok=True)
                (Path(output_dir) / "model.safetensors").write_text("merged", encoding="utf-8")

        class DummyAutoModel:
            @classmethod
            def from_pretrained(cls, model_path, trust_remote_code=True, **kwargs):
                assert Path(model_path) == model_dir
                return DummyModel()

        fake_transformers.AutoTokenizer = DummyTokenizer
        fake_transformers.AutoModelForCausalLM = DummyAutoModel

        fake_peft = types.ModuleType("peft")

        class DummyPeftModel:
            @classmethod
            def from_pretrained(cls, model, adapter_path, **kwargs):
                assert Path(adapter_path) == adapter_dir
                return cls()

            def merge_and_unload(self):
                return DummyModel()

        fake_peft.PeftModel = DummyPeftModel

        monkeypatch.setitem(sys.modules, "transformers", fake_transformers)
        monkeypatch.setitem(sys.modules, "peft", fake_peft)
        monkeypatch.setattr(models_api, "get_models_dir", lambda: models_dir)
        monkeypatch.setattr(models_api, "get_settings", lambda: DummySettings())

        response = client.post(
            f"/models/tiny-model/merge",
            json={"output_name": "tiny-merged", "adapter_path": str(adapter_dir)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["model_id"] == "tiny-model"
        assert Path(data["path"]) == outputs_dir / "exports" / "tiny-merged"
        manifest = Path(data["path"]) / "export_config.json"
        assert manifest.exists()
        manifest_data = manifest.read_text(encoding="utf-8")
        manifest_json = json.loads(manifest_data)
        assert manifest_json["format"] == "lora-merged"
        assert manifest_json["adapter_path_raw"] == str(adapter_dir)

    def test_merge_lora_falls_back_to_training_history_adapter(self, tmp_path, monkeypatch):
        """测试未显式传 adapter 时会从训练历史中兜底查找"""
        models_dir = tmp_path / "models"
        outputs_dir = tmp_path / "outputs"
        model_dir = models_dir / "tiny-model"
        history_adapter = tmp_path / "outputs" / "train_abc" / "lora_adapter"
        model_dir.mkdir(parents=True)
        history_adapter.mkdir(parents=True)
        (model_dir / "config.json").write_text('{"model_name":"Tiny","type":"base"}', encoding="utf-8")
        (history_adapter / "adapter_config.json").write_text("{}", encoding="utf-8")

        class DummySettings:
            outputs_dir_resolved = outputs_dir

        fake_transformers = types.ModuleType("transformers")

        class DummyTokenizer:
            @classmethod
            def from_pretrained(cls, model_path, trust_remote_code=True):
                assert Path(model_path) == model_dir
                return cls()

            def save_pretrained(self, output_dir):
                Path(output_dir).mkdir(parents=True, exist_ok=True)
                (Path(output_dir) / "tokenizer.json").write_text("tokenizer", encoding="utf-8")

        class DummyModel:
            def save_pretrained(self, output_dir, safe_serialization=True):
                Path(output_dir).mkdir(parents=True, exist_ok=True)
                (Path(output_dir) / "model.safetensors").write_text("merged", encoding="utf-8")

        class DummyAutoModel:
            @classmethod
            def from_pretrained(cls, model_path, trust_remote_code=True, **kwargs):
                assert Path(model_path) == model_dir
                return DummyModel()

        fake_transformers.AutoTokenizer = DummyTokenizer
        fake_transformers.AutoModelForCausalLM = DummyAutoModel

        fake_peft = types.ModuleType("peft")

        class DummyPeftModel:
            @classmethod
            def from_pretrained(cls, model, adapter_path, **kwargs):
                assert Path(adapter_path) == history_adapter
                return cls()

            def merge_and_unload(self):
                return DummyModel()

        fake_peft.PeftModel = DummyPeftModel

        fake_record = SimpleNamespace(
            id="train-abc",
            model_name="tiny-model",
            status="completed",
            checkpoint_path=str(history_adapter),
            start_time="2026-04-20T10:00:00",
            end_time="2026-04-20T10:30:00",
        )

        monkeypatch.setitem(sys.modules, "transformers", fake_transformers)
        monkeypatch.setitem(sys.modules, "peft", fake_peft)
        monkeypatch.setattr(models_api, "get_models_dir", lambda: models_dir)
        monkeypatch.setattr(models_api, "get_settings", lambda: DummySettings())
        monkeypatch.setattr(
            models_api,
            "get_training_context",
            lambda: SimpleNamespace(state=SimpleNamespace(get_history=lambda: [fake_record])),
            raising=False,
        )

        response = client.post(
            "/models/tiny-model/merge",
            json={"output_name": "tiny-merged-history"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["manifest"]["adapter_path"] == str(history_adapter)
        manifest = Path(data["path"]) / "export_config.json"
        assert manifest.exists()
        assert '"training_id": "train-abc"' in manifest.read_text(encoding="utf-8")
