from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import deployment, evaluation
from core.training_state import TrainingRecord


class DummySettings:
    def __init__(self, root: Path):
        self.outputs_dir_resolved = root / "outputs"
        self.datasets_dir_resolved = root / "datasets"


def test_structured_evaluation_metrics(tmp_path: Path, monkeypatch):
    settings = DummySettings(tmp_path)
    monkeypatch.setattr(evaluation, "get_settings", lambda: settings)
    app = FastAPI()
    app.include_router(evaluation.router, prefix="/evaluation")

    response = TestClient(app).post(
        "/evaluation/runs",
        json={
            "scenario": "structured_extraction",
            "base_model": "base",
            "finetuned_model": "adapter",
            "cases": [
                {
                    "prompt": "抽取金额",
                    "schema": {"amount": "number"},
                    "base_output": "金额是 19.9",
                    "finetuned_output": "{\"amount\": 19.9}",
                }
            ],
        },
    )

    assert response.status_code == 200
    run_id = response.json()["run_id"]
    
    import time
    for _ in range(50):
        response = TestClient(app).get(f"/evaluation/runs/{run_id}")
        payload = response.json()
        if payload["status"] not in ("pending", "running"):
            break
        time.sleep(0.1)

    assert payload["metrics"]["json_valid_rate"] == 1.0
    assert payload["metrics"]["schema_match_rate"] == 1.0
    assert payload["failed_cases"] == []


def test_evaluation_runs_real_inference_when_outputs_missing(tmp_path: Path, monkeypatch):
    settings = DummySettings(tmp_path)
    monkeypatch.setattr(evaluation, "get_settings", lambda: settings)

    async def fake_inference(**kwargs):
        if kwargs["model"] == "base":
            return "金额是 19.9"
        return "{\"amount\": 19.9}"

    monkeypatch.setattr(evaluation, "run_model_inference", fake_inference)
    app = FastAPI()
    app.include_router(evaluation.router, prefix="/evaluation")

    response = TestClient(app).post(
        "/evaluation/runs",
        json={
            "scenario": "structured_extraction",
            "base_model": "base",
            "finetuned_model": "fine",
            "backend": "ollama",
            "cases": [
                {
                    "prompt": "订单金额 19.9 元",
                    "schema": {"amount": "number"},
                }
            ],
        },
    )

    assert response.status_code == 200
    run_id = response.json()["run_id"]
    
    import time
    for _ in range(50):
        response = TestClient(app).get(f"/evaluation/runs/{run_id}")
        payload = response.json()
        if payload["status"] not in ("pending", "running"):
            break
        time.sleep(0.1)

    assert payload["base_outputs"] == ["金额是 19.9"]
    assert payload["finetuned_outputs"] == ['{"amount": 19.9}']
    assert payload["metrics"]["json_valid_rate"] == 1.0
    assert payload["run_inference"] is True


def test_evaluation_auto_merges_adapter_for_real_inference(tmp_path: Path, monkeypatch):
    settings = DummySettings(tmp_path)
    monkeypatch.setattr(evaluation, "get_settings", lambda: settings)

    def fake_merge(request, run_id):
        return {
            "merged_model_path": str(tmp_path / "outputs" / "evaluation-merged" / run_id),
            "adapter_path": request.adapter_path,
            "backend": "huggingface",
        }

    async def fake_inference(**kwargs):
        if kwargs["model"] == "base":
            return "金额是 19.9"
        assert kwargs["backend"] == "huggingface"
        assert "evaluation-merged" in kwargs["model"]
        return "{\"amount\": 19.9}"

    monkeypatch.setattr(evaluation, "_merge_adapter_for_evaluation", fake_merge)
    monkeypatch.setattr(evaluation, "run_model_inference", fake_inference)
    app = FastAPI()
    app.include_router(evaluation.router, prefix="/evaluation")

    response = TestClient(app).post(
        "/evaluation/runs",
        json={
            "scenario": "structured_extraction",
            "base_model": "base",
            "adapter_path": "outputs/train_1/lora_adapter",
            "backend": "ollama",
            "cases": [
                {
                    "prompt": "订单金额 19.9 元",
                    "schema": {"amount": "number"},
                }
            ],
        },
    )

    assert response.status_code == 200
    run_id = response.json()["run_id"]
    
    import time
    for _ in range(50):
        response = TestClient(app).get(f"/evaluation/runs/{run_id}")
        payload = response.json()
        if payload["status"] not in ("pending", "running"):
            break
        time.sleep(0.1)

    assert payload["adapter_merge"]["backend"] == "huggingface"
    assert payload["adapter_merge"]["adapter_path"] == "outputs/train_1/lora_adapter"
    assert "evaluation-merged" in payload["finetuned_model"]
    assert payload["finetuned_outputs"] == ['{"amount": 19.9}']
    assert payload["metrics"]["json_valid_rate"] == 1.0


def test_deployment_package_contains_examples(tmp_path: Path, monkeypatch):
    settings = DummySettings(tmp_path)
    monkeypatch.setattr(deployment, "get_settings", lambda: settings)
    app = FastAPI()
    app.include_router(deployment.router, prefix="/deployment")

    response = TestClient(app).post(
        "/deployment/packages",
        json={
            "training_task_id": "train_1",
            "base_model": "qwen2.5:7b",
            "adapter_path": "outputs/train_1/adapter",
            "model_alias": "support-v1",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["training_task_id"] == "train_1"
    assert "FROM qwen2.5:7b" in payload["ollama_modelfile"]
    assert "curl" in payload["openai_compatible_examples"]
    assert payload["env_template"]["MODEL_NAME"] == "support-v1"


def test_deployment_package_resolves_training_history_metadata(tmp_path: Path, monkeypatch):
    settings = DummySettings(tmp_path)
    monkeypatch.setattr(deployment, "get_settings", lambda: settings)

    record = TrainingRecord(
        id="train_history_1",
        model_name="display-model",
        dataset_name="dataset",
        base_model_id="qwen-local",
        dataset_id="dataset",
        task_goal="qa_assistant",
        method="qlora",
        status="completed",
        start_time="2026-04-24T00:00:00",
        config={"model_id": "qwen-local", "dataset_id": "dataset"},
        output_path=str(tmp_path / "outputs" / "train_history_1"),
        adapter_path="outputs/train_history_1/lora_adapter",
        checkpoint_path="outputs/train_history_1/lora_adapter",
    )

    class FakeState:
        def get_history(self):
            return [record]

    class FakeContext:
        state = FakeState()

    monkeypatch.setattr(deployment, "get_training_context", lambda: FakeContext())

    app = FastAPI()
    app.include_router(deployment.router, prefix="/deployment")

    response = TestClient(app).post(
        "/deployment/packages",
        json={
            "training_task_id": "train_history_1",
            "model_alias": "support-from-history",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["base_model"] == "qwen-local"
    assert payload["adapter_path"] == "outputs/train_history_1/lora_adapter"
    assert payload["env_template"]["MODEL_NAME"] == "support-from-history"


def test_deployment_package_list_returns_recent_summaries(tmp_path: Path, monkeypatch):
    settings = DummySettings(tmp_path)
    monkeypatch.setattr(deployment, "get_settings", lambda: settings)
    app = FastAPI()
    app.include_router(deployment.router, prefix="/deployment")
    client = TestClient(app)

    first = client.post(
        "/deployment/packages",
        json={
            "training_task_id": "train_old",
            "base_model": "base-old",
            "adapter_path": "outputs/train_old/adapter",
            "model_alias": "old-model",
        },
    ).json()
    second = client.post(
        "/deployment/packages",
        json={
            "training_task_id": "train_new",
            "base_model": "base-new",
            "adapter_path": "outputs/train_new/adapter",
            "model_alias": "new-model",
        },
    ).json()

    response = client.get("/deployment/packages")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    assert payload[0]["package_id"] == second["package_id"]
    assert payload[0]["model_name"] == "new-model"
    assert payload[1]["package_id"] == first["package_id"]


def test_deployment_package_delete_removes_package(tmp_path: Path, monkeypatch):
    settings = DummySettings(tmp_path)
    monkeypatch.setattr(deployment, "get_settings", lambda: settings)
    app = FastAPI()
    app.include_router(deployment.router, prefix="/deployment")
    client = TestClient(app)

    created = client.post(
        "/deployment/packages",
        json={
            "training_task_id": "train_delete",
            "base_model": "base-delete",
            "adapter_path": "outputs/train_delete/adapter",
            "model_alias": "delete-model",
        },
    ).json()

    delete_response = client.delete(f"/deployment/packages/{created['package_id']}")
    get_response = client.get(f"/deployment/packages/{created['package_id']}")
    list_response = client.get("/deployment/packages")

    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] is True
    assert get_response.status_code == 404
    assert list_response.json() == []
