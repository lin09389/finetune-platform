"""
训练 API 测试
"""
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import get_settings
from core.training_state import TrainingRecord, TrainingState

TRAINING_MODULE_PATH = Path(__file__).resolve().parents[1] / "api" / "training.py"
TRAINING_SPEC = importlib.util.spec_from_file_location("training_module", TRAINING_MODULE_PATH)
training_module = importlib.util.module_from_spec(TRAINING_SPEC)
assert TRAINING_SPEC and TRAINING_SPEC.loader
TRAINING_SPEC.loader.exec_module(training_module)

ProgressCallback = training_module.ProgressCallback
TrainingConfigInput = training_module.TrainingConfigInput
TrainingValidator = training_module.TrainingValidator
ValidationResult = training_module.ValidationResult
detect_dataset_sample_format = training_module.detect_dataset_sample_format
load_dataset = training_module.load_dataset
resume_training = training_module.resume_training
split_train_test_dataset = training_module.split_train_test_dataset
validate_release_supported_features = training_module._validate_release_supported_features
get_checkpoints = training_module.get_checkpoints

try:
    from fastapi.testclient import TestClient
    from main import app
except Exception as exc:  # pragma: no cover - depends on unrelated app wiring
    TestClient = None
    app = None
    APP_IMPORT_ERROR = exc
else:
    APP_IMPORT_ERROR = None

client = TestClient(app) if app is not None else None


@pytest.mark.skipif(app is None, reason=f"FastAPI app import failed: {APP_IMPORT_ERROR}")
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


class DummyTokenizer:
    pad_token_id = 0
    pad_token = "<pad>"
    eos_token = "</s>"

    def __call__(self, texts, truncation=True, max_length=512, padding="max_length"):
        if isinstance(texts, str):
            texts = [texts]
        return {
            "input_ids": [[1, 2, 3, 0] for _ in texts],
            "attention_mask": [[1, 1, 1, 0] for _ in texts],
        }

    def encode(self, text, add_special_tokens=False):
        return [1]


class TestTrainingDatasetValidation:
    """训练数据格式校验测试"""

    @pytest.mark.parametrize(
        ("sample", "expected_format"),
        [
            ({"messages": [{"role": "user", "content": "hi"}]}, "messages"),
            ({"text": "hello"}, "text"),
            ({"content": "hello"}, "content"),
            ({"instruction": "say hi", "output": "hi"}, "instruction+output"),
            (
                {"instruction": "translate", "input": "hello", "output": "你好"},
                "instruction+input+output",
            ),
        ],
    )
    def test_detect_dataset_sample_format_accepts_supported_formats(self, sample, expected_format):
        assert detect_dataset_sample_format(sample) == expected_format

    def test_detect_dataset_sample_format_rejects_missing_alpaca_output(self):
        with pytest.raises(ValueError, match="output"):
            detect_dataset_sample_format({"instruction": "say hi"})

    def test_detect_dataset_sample_format_rejects_unsupported_fields(self):
        with pytest.raises(ValueError, match="Unsupported dataset sample format"):
            detect_dataset_sample_format({"prompt": "hi", "answer": "hello"})

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "sample",
        [
            {"messages": [{"role": "user", "content": "hi"}]},
            {"text": "hello"},
            {"content": "hello"},
            {"instruction": "say hi", "output": "hi"},
            {"instruction": "translate", "input": "hello", "output": "你好"},
        ],
    )
    async def test_validate_dataset_accepts_supported_formats(self, tmp_path, sample):
        dataset_dir = tmp_path / "datasets" / "supported"
        dataset_dir.mkdir(parents=True)
        (dataset_dir / "data.json").write_text(json.dumps([sample], ensure_ascii=False), encoding="utf-8")

        settings = get_settings()
        original_datasets_dir = settings.datasets_dir
        settings.datasets_dir = tmp_path / "datasets"
        try:
            config = TrainingConfigInput(model_id="dummy-model", dataset_id="supported")
            result = ValidationResult()
            await TrainingValidator._validate_dataset(config, settings, result)
        finally:
            settings.datasets_dir = original_datasets_dir

        assert result.errors == []

    @pytest.mark.asyncio
    async def test_validate_dataset_rejects_missing_alpaca_output(self, tmp_path):
        dataset_dir = tmp_path / "datasets" / "missing-output"
        dataset_dir.mkdir(parents=True)
        (dataset_dir / "data.json").write_text(
            json.dumps([{"instruction": "say hi"}], ensure_ascii=False),
            encoding="utf-8",
        )

        settings = get_settings()
        original_datasets_dir = settings.datasets_dir
        settings.datasets_dir = tmp_path / "datasets"
        try:
            config = TrainingConfigInput(model_id="dummy-model", dataset_id="missing-output")
            result = ValidationResult()
            await TrainingValidator._validate_dataset(config, settings, result)
        finally:
            settings.datasets_dir = original_datasets_dir

        assert result.errors
        assert "output" in result.errors[0]

    @pytest.mark.asyncio
    async def test_validate_dataset_rejects_unsupported_fields(self, tmp_path):
        dataset_dir = tmp_path / "datasets" / "unsupported"
        dataset_dir.mkdir(parents=True)
        (dataset_dir / "data.json").write_text(
            json.dumps([{"prompt": "hi", "answer": "hello"}], ensure_ascii=False),
            encoding="utf-8",
        )

        settings = get_settings()
        original_datasets_dir = settings.datasets_dir
        settings.datasets_dir = tmp_path / "datasets"
        try:
            config = TrainingConfigInput(model_id="dummy-model", dataset_id="unsupported")
            result = ValidationResult()
            await TrainingValidator._validate_dataset(config, settings, result)
        finally:
            settings.datasets_dir = original_datasets_dir

        assert result.errors
        assert "Unsupported dataset sample format" in result.errors[0]

    def test_alpaca_dataset_passes_validator_and_loader(self, tmp_path):
        dataset_dir = tmp_path / "datasets" / "alpaca"
        dataset_dir.mkdir(parents=True)
        dataset_file = dataset_dir / "data.json"
        dataset_file.write_text(
            json.dumps(
                [
                    {"instruction": "translate", "input": "hello", "output": "你好"},
                    {"instruction": "translate", "input": "world", "output": "世界"},
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        settings = get_settings()
        original_datasets_dir = settings.datasets_dir
        settings.datasets_dir = tmp_path / "datasets"
        try:
            config = TrainingConfigInput(model_id="dummy-model", dataset_id="alpaca")
            result = ValidationResult()
            import asyncio

            asyncio.run(TrainingValidator._validate_dataset(config, settings, result))
        finally:
            settings.datasets_dir = original_datasets_dir

        dataset = load_dataset(str(dataset_file), DummyTokenizer(), max_length=16)

        assert result.errors == []
        assert len(dataset["train"]) + len(dataset["test"]) == 2
        sample = dataset["train"][0] if len(dataset["train"]) else dataset["test"][0]
        assert "input_ids" in sample
        assert "labels" in sample

    def test_single_record_dataset_keeps_train_split(self, tmp_path):
        dataset_file = tmp_path / "single.json"
        dataset_file.write_text(
            json.dumps([{"instruction": "translate", "output": "你好"}], ensure_ascii=False),
            encoding="utf-8",
        )

        dataset = load_dataset(str(dataset_file), DummyTokenizer(), max_length=16)

        assert len(dataset["train"]) == 1
        assert len(dataset["test"]) == 0

    def test_split_train_test_dataset_keeps_small_dataset_non_empty(self):
        from datasets import Dataset

        dataset = Dataset.from_list([{"text": "a"}, {"text": "b"}])
        split = split_train_test_dataset(dataset)

        assert len(split["train"]) == 1
        assert len(split["test"]) == 1


class TestTrainingReleaseFeatureGuards:
    def test_release_guard_rejects_dora_flag(self):
        config = TrainingConfigInput(model_id="model", dataset_id="dataset", use_dora=True)

        with pytest.raises(training_module.HTTPException, match="DoRA"):
            validate_release_supported_features(config)

    def test_release_guard_rejects_dora_method(self):
        config = TrainingConfigInput(model_id="model", dataset_id="dataset", method="dora")

        with pytest.raises(training_module.HTTPException, match="DoRA"):
            validate_release_supported_features(config)

    @pytest.mark.parametrize(
        ("field_name", "value", "expected_message"),
        [
            ("use_lora_plus", True, "LoRA+"),
            ("use_galore", True, "GaLore"),
        ],
    )
    def test_release_guard_rejects_experimental_features(self, field_name, value, expected_message):
        config = TrainingConfigInput(model_id="model", dataset_id="dataset", **{field_name: value})

        with pytest.raises(training_module.HTTPException, match=expected_message):
            validate_release_supported_features(config)

    def test_release_guard_limits_swift_to_lora_variants(self):
        config = TrainingConfigInput(model_id="model", dataset_id="dataset", method="full")

        with pytest.raises(training_module.HTTPException, match="SWIFT"):
            validate_release_supported_features(config, backend="swift")

    def test_release_guard_allows_standard_release_path(self):
        config = TrainingConfigInput(model_id="model", dataset_id="dataset", method="qlora")

        validate_release_supported_features(config)

    @pytest.mark.asyncio
    async def test_get_checkpoints_uses_record_output_path(self, tmp_path, monkeypatch):
        task_id = "checkpoint-task"
        output_dir = tmp_path / "custom-output"
        checkpoint_dir = output_dir / "checkpoints"
        checkpoint_dir.mkdir(parents=True)
        (checkpoint_dir / "checkpoint-20").mkdir()
        time_10 = checkpoint_dir / "checkpoint-10"
        time_10.mkdir()

        record = TrainingRecord(
            id=task_id,
            model_name="demo-model",
            dataset_name="demo-dataset",
            method="qlora",
            status="completed",
            start_time="2026-04-02T00:00:00",
            config={},
            output_path=str(output_dir),
        )

        class FakeState:
            def get_history(self):
                return [record]

        class FakeContext:
            def __init__(self):
                self._state = FakeState()
            @property
            def state(self):
                return self._state

        monkeypatch.setattr(training_module, "get_training_context", FakeContext)
        monkeypatch.setattr(training_module, "get_settings", lambda: get_settings())

        checkpoints = await get_checkpoints(task_id)

        assert [item["step"] for item in checkpoints] == [10, 20]
        assert all(item["path"].startswith(str(checkpoint_dir)) for item in checkpoints)

    def test_progress_callback_accepts_event_loop_argument(self, tmp_path):
        state = TrainingState(tmp_path / "history.json")
        record = TrainingRecord(
            id="task-1",
            model_name="model",
            dataset_name="dataset",
            method="qlora",
            status="running",
            start_time="2026-04-02T00:00:00",
            config={},
            output_path=str(tmp_path),
        )
        config = TrainingConfigInput(model_id="model", dataset_id="dataset")

        callback = ProgressCallback(
            total_steps=10,
            start_time=__import__("datetime").datetime.now(),
            state=state,
            record=record,
            config=config,
            event_loop=None,
        )

        assert callback._event_loop is None
        state.cleanup()

    @pytest.mark.asyncio
    async def test_resume_training_reuses_task_id_and_output_path(self, tmp_path, monkeypatch):
        task_id = "12345678-abcd-efgh"
        output_dir = tmp_path / f"train_{task_id[:8]}"
        checkpoint_dir = output_dir / "checkpoints" / "checkpoint-10"
        checkpoint_dir.mkdir(parents=True)

        settings = get_settings()
        original_outputs_dir = settings.outputs_dir
        original_models_dir = settings.models_dir
        original_datasets_dir = settings.datasets_dir
        settings.outputs_dir = tmp_path
        settings.models_dir = tmp_path / "models"
        settings.datasets_dir = tmp_path / "datasets"

        model_dir = settings.models_dir / "demo-model"
        model_dir.mkdir(parents=True)
        dataset_dir = settings.datasets_dir / "demo-dataset"
        dataset_dir.mkdir(parents=True)
        (dataset_dir / "data.json").write_text(
            json.dumps([{"instruction": "hi", "output": "there"}], ensure_ascii=False),
            encoding="utf-8",
        )

        history_record = TrainingRecord(
            id=task_id,
            model_name="demo-model",
            dataset_name="demo-dataset",
            method="qlora",
            status="stopped",
            start_time="2026-04-02T00:00:00",
            config={
                "model_id": "demo-model",
                "dataset_id": "demo-dataset",
                "method": "qlora",
            },
            output_path=str(output_dir),
        )

        class FakeState:
            def is_training(self):
                return False

            def get_history(self):
                return [history_record]

        captured = {}

        def fake_start_training_task(**kwargs):
            captured.update(kwargs)
            return {"ok": True}

        monkeypatch.setattr(training_module, "get_training_context", lambda: type('FakeCtx', (), {'state': FakeState()}))
        monkeypatch.setattr(training_module, "get_settings", lambda: settings)
        monkeypatch.setattr(training_module, "_start_training_task", fake_start_training_task)

        try:
            result = await resume_training(task_id, "checkpoint-10")
        finally:
            settings.outputs_dir = original_outputs_dir
            settings.models_dir = original_models_dir
            settings.datasets_dir = original_datasets_dir

        assert result == {"ok": True}
        assert captured["record_id"] == task_id
        assert captured["output_path"] == output_dir
        assert captured["config"].resume_from_checkpoint == str(checkpoint_dir)

    @pytest.mark.asyncio
    async def test_resume_training_uses_record_output_path_for_checkpoint_lookup(self, tmp_path, monkeypatch):
        task_id = "resume-custom"
        output_dir = tmp_path / "nested" / "custom-output"
        checkpoint_dir = output_dir / "checkpoints" / "checkpoint-10"
        checkpoint_dir.mkdir(parents=True)

        settings = get_settings()
        original_outputs_dir = settings.outputs_dir
        original_models_dir = settings.models_dir
        original_datasets_dir = settings.datasets_dir
        settings.outputs_dir = tmp_path / "outputs"
        settings.models_dir = tmp_path / "models"
        settings.datasets_dir = tmp_path / "datasets"

        model_dir = settings.models_dir / "demo-model"
        model_dir.mkdir(parents=True)
        dataset_dir = settings.datasets_dir / "demo-dataset"
        dataset_dir.mkdir(parents=True)
        (dataset_dir / "data.json").write_text(
            json.dumps([{"instruction": "hi", "output": "there"}], ensure_ascii=False),
            encoding="utf-8",
        )

        history_record = TrainingRecord(
            id=task_id,
            model_name="demo-model",
            dataset_name="demo-dataset",
            method="qlora",
            status="stopped",
            start_time="2026-04-02T00:00:00",
            config={
                "model_id": "demo-model",
                "dataset_id": "demo-dataset",
                "method": "qlora",
            },
            output_path=str(output_dir),
        )

        class FakeState:
            def is_training(self):
                return False

            def get_history(self):
                return [history_record]

        captured = {}

        def fake_start_training_task(**kwargs):
            captured.update(kwargs)
            return {"ok": True}

        monkeypatch.setattr(training_module, "get_training_context", lambda: type('FakeCtx', (), {'state': FakeState()}))
        monkeypatch.setattr(training_module, "get_settings", lambda: settings)
        monkeypatch.setattr(training_module, "_start_training_task", fake_start_training_task)

        try:
            result = await resume_training(task_id, "checkpoint-10")
        finally:
            settings.outputs_dir = original_outputs_dir
            settings.models_dir = original_models_dir
            settings.datasets_dir = original_datasets_dir

        assert result == {"ok": True}
        assert captured["output_path"] == output_dir
        assert captured["config"].resume_from_checkpoint == str(checkpoint_dir)
