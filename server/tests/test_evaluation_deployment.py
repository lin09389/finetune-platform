from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import deployment, evaluation
from core.training_state import TrainingRecord


class DummySettings:
    def __init__(self, root: Path):
        self.outputs_dir_resolved = root / "outputs"
        self.datasets_dir_resolved = root / "datasets"


def _write_eval_run(
    root: Path,
    run_id: str,
    *,
    training_task_id: str,
    base_model: str,
    adapter_path: str | None = None,
    scenario: str = "qa_assistant",
    metrics: dict | None = None,
):
    eval_dir = root / "outputs" / "evaluations"
    eval_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": run_id,
        "status": "completed",
        "scenario": scenario,
        "training_task_id": training_task_id,
        "base_model": base_model,
        "adapter_path": adapter_path,
        "metrics": metrics or {"good_rate": 0.8, "win_rate": 0.7},
    }
    (eval_dir / f"{run_id}.json").write_text(json.dumps(payload), encoding="utf-8")
    return payload


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
        prompts = kwargs["prompts"]
        if kwargs["model"] == "base":
            return ["金额是 19.9" for _ in prompts]
        return ["{\"amount\": 19.9}" for _ in prompts]

    monkeypatch.setattr(evaluation, "run_model_inference_batch_with_retry", fake_inference)
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

    async def fake_inference(**kwargs):
        prompts = kwargs["prompts"]
        if kwargs.get("lora_adapter") is None:
            return ["金额是 19.9" for _ in prompts]
        assert kwargs["backend"] == "huggingface"
        assert kwargs["model"] == "base"
        return ["{\"amount\": 19.9}" for _ in prompts]

    monkeypatch.setattr(evaluation, "run_model_inference_batch_with_retry", fake_inference)
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
    assert payload["finetuned_model"] == "base"
    assert payload["finetuned_outputs"] == ['{"amount": 19.9}']
    assert payload["metrics"]["json_valid_rate"] == 1.0


def test_deployment_package_contains_examples(tmp_path: Path, monkeypatch):
    settings = DummySettings(tmp_path)
    monkeypatch.setattr(deployment, "get_settings", lambda: settings)
    adapter_dir = tmp_path / "outputs" / "train_1" / "adapter"
    adapter_dir.mkdir(parents=True)
    _write_eval_run(tmp_path, "eval_pass", training_task_id="train_1", base_model="qwen2.5:7b", adapter_path=str(adapter_dir))
    app = FastAPI()
    app.include_router(deployment.router, prefix="/deployment")

    response = TestClient(app).post(
        "/deployment/packages",
        json={
            "training_task_id": "train_1",
            "base_model": "qwen2.5:7b",
            "adapter_path": str(adapter_dir),
            "evaluation_run_id": "eval_pass",
            "model_alias": "support-v1",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["training_task_id"] == "train_1"
    assert payload["evaluation_gate"]["passed"] is True
    assert "FROM qwen2.5:7b" in payload["ollama_modelfile"]
    assert "curl" in payload["openai_compatible_examples"]
    assert payload["env_template"]["MODEL_NAME"] == "support-v1"


def test_deployment_package_resolves_training_history_metadata(tmp_path: Path, monkeypatch):
    settings = DummySettings(tmp_path)
    monkeypatch.setattr(deployment, "get_settings", lambda: settings)
    adapter_dir = tmp_path / "outputs" / "train_history_1" / "lora_adapter"
    adapter_dir.mkdir(parents=True)
    _write_eval_run(tmp_path, "eval_history", training_task_id="train_history_1", base_model="qwen-local", adapter_path=str(adapter_dir))

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
        adapter_path=str(adapter_dir),
        checkpoint_path=str(adapter_dir),
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
            "evaluation_run_id": "eval_history",
            "model_alias": "support-from-history",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["base_model"] == "qwen-local"
    assert payload["adapter_path"] == str(adapter_dir)
    assert payload["env_template"]["MODEL_NAME"] == "support-from-history"


def test_deployment_package_list_returns_recent_summaries(tmp_path: Path, monkeypatch):
    settings = DummySettings(tmp_path)
    monkeypatch.setattr(deployment, "get_settings", lambda: settings)
    old_adapter = tmp_path / "outputs" / "train_old" / "adapter"
    new_adapter = tmp_path / "outputs" / "train_new" / "adapter"
    old_adapter.mkdir(parents=True)
    new_adapter.mkdir(parents=True)
    _write_eval_run(tmp_path, "eval_old", training_task_id="train_old", base_model="base-old", adapter_path=str(old_adapter))
    _write_eval_run(tmp_path, "eval_new", training_task_id="train_new", base_model="base-new", adapter_path=str(new_adapter))
    app = FastAPI()
    app.include_router(deployment.router, prefix="/deployment")
    client = TestClient(app)

    first = client.post(
        "/deployment/packages",
        json={
            "training_task_id": "train_old",
            "base_model": "base-old",
            "adapter_path": str(old_adapter),
            "evaluation_run_id": "eval_old",
            "model_alias": "old-model",
        },
    ).json()
    second = client.post(
        "/deployment/packages",
        json={
            "training_task_id": "train_new",
            "base_model": "base-new",
            "adapter_path": str(new_adapter),
            "evaluation_run_id": "eval_new",
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
    adapter_dir = tmp_path / "outputs" / "train_delete" / "adapter"
    adapter_dir.mkdir(parents=True)
    _write_eval_run(tmp_path, "eval_delete", training_task_id="train_delete", base_model="base-delete", adapter_path=str(adapter_dir))
    app = FastAPI()
    app.include_router(deployment.router, prefix="/deployment")
    client = TestClient(app)

    created = client.post(
        "/deployment/packages",
        json={
            "training_task_id": "train_delete",
            "base_model": "base-delete",
            "adapter_path": str(adapter_dir),
            "evaluation_run_id": "eval_delete",
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


def test_deployment_package_requires_passing_evaluation(tmp_path: Path, monkeypatch):
    settings = DummySettings(tmp_path)
    monkeypatch.setattr(deployment, "get_settings", lambda: settings)
    adapter_dir = tmp_path / "outputs" / "train_blocked" / "adapter"
    adapter_dir.mkdir(parents=True)
    _write_eval_run(
        tmp_path,
        "eval_blocked",
        training_task_id="train_blocked",
        base_model="base-blocked",
        adapter_path=str(adapter_dir),
        metrics={"good_rate": 0.2, "win_rate": 0.1},
    )

    app = FastAPI()
    app.include_router(deployment.router, prefix="/deployment")
    client = TestClient(app)

    missing_eval = client.post(
        "/deployment/packages",
        json={
            "training_task_id": "train_blocked",
            "base_model": "base-blocked",
            "adapter_path": str(adapter_dir),
        },
    )
    failed_gate = client.post(
        "/deployment/packages",
        json={
            "training_task_id": "train_blocked",
            "base_model": "base-blocked",
            "adapter_path": str(adapter_dir),
            "evaluation_run_id": "eval_blocked",
        },
    )

    assert missing_eval.status_code == 400
    assert failed_gate.status_code == 400
    assert "评估门禁未通过" in failed_gate.json()["detail"]
