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
    default_metrics = {
        "good_rate": 0.8,
        "win_rate": 0.8,
        "net_win_rate": 0.6,
        "human_score_count": 5,
    }
    default_metrics.update(metrics or {})
    payload = {
        "run_id": run_id,
        "status": "completed",
        "scenario": scenario,
        "training_task_id": training_task_id,
        "base_model": base_model,
        "adapter_path": adapter_path,
        "metrics": default_metrics,
        "data_provenance": {
            "source": "independent_dataset",
            "isolated_from_training": True,
        },
        "cases": [
            {
                "prompt": "hello",
                "base_output": "base answer",
                "finetuned_output": "fine answer",
                "human_score": {"score": "good"},
            }
            for _ in range(5)
        ],
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
                    "expected_output": {"amount": 19.9},
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
    assert payload["metrics"]["expected_match_rate"] == 1.0
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
    assert payload["finetuned_model"] is None
    assert payload["adapter_merge"]["mode"] == "dynamic_lora"
    assert payload["finetuned_outputs"] == ['{"amount": 19.9}']
    assert payload["metrics"]["json_valid_rate"] == 1.0


def test_training_linked_evaluation_resolves_release_and_adapter(tmp_path: Path, monkeypatch):
    adapter_dir = tmp_path / "outputs" / "train_linked" / "lora_adapter"
    adapter_dir.mkdir(parents=True)
    snapshot_path = adapter_dir.parent / "evaluation_snapshot.json"
    snapshot_path.write_text(json.dumps([{"prompt": "held out"}]), encoding="utf-8")
    record = TrainingRecord(
        id="train_linked",
        model_name="display-name",
        dataset_name="dataset-linked",
        base_model_id="base-linked",
        dataset_id="dataset-linked",
        task_goal="structured_extraction",
        method="qlora",
        status="completed",
        start_time="2026-04-24T00:00:00",
        config={"model_id": "base-linked", "dataset_id": "dataset-linked"},
        output_path=str(adapter_dir.parent),
        adapter_path=str(adapter_dir),
        checkpoint_path=str(adapter_dir),
        release_id="release-linked",
        evaluation_snapshot_path=str(snapshot_path),
    )
    monkeypatch.setattr(evaluation, "_find_training_record", lambda _task_id: record)

    request = evaluation.EvaluationRunRequest(
        training_task_id="train_linked",
        base_model="base-linked",
        cases=[{"prompt": "hello"}],
    )
    resolved = evaluation._resolve_evaluation_request(request)

    assert resolved.adapter_path == str(adapter_dir)
    assert resolved.release_id == "release-linked"
    assert resolved.test_dataset_id is None
    assert resolved.evaluation_snapshot_path == str(snapshot_path)
    assert resolved.scenario == "structured_extraction"


def test_training_linked_evaluation_rejects_non_completed_record(tmp_path: Path, monkeypatch):
    record = TrainingRecord(
        id="train_stopped",
        model_name="base",
        dataset_name="dataset",
        method="qlora",
        status="stopped",
        start_time="2026-04-24T00:00:00",
        config={"model_id": "base", "dataset_id": "dataset"},
        output_path=str(tmp_path),
    )
    monkeypatch.setattr(evaluation, "_find_training_record", lambda _task_id: record)

    request = evaluation.EvaluationRunRequest(
        training_task_id="train_stopped",
        base_model="base",
        cases=[{"prompt": "hello"}],
    )

    import pytest

    with pytest.raises(Exception) as exc:
        evaluation._resolve_evaluation_request(request)
    assert "只有已完成" in str(exc.value)


def test_evaluation_rejects_disabled_dynamic_adapter_without_merged_model(
    tmp_path: Path,
    monkeypatch,
):
    settings = DummySettings(tmp_path)
    monkeypatch.setattr(evaluation, "get_settings", lambda: settings)
    app = FastAPI()
    app.include_router(evaluation.router, prefix="/evaluation")

    response = TestClient(app).post(
        "/evaluation/runs",
        json={
            "base_model": "base",
            "adapter_path": "adapter",
            "auto_merge_adapter": False,
            "cases": [{"prompt": "hello"}],
        },
    )

    assert response.status_code == 400
    assert "必须提供已合并的 finetuned_model" in response.json()["detail"]


def test_evaluation_rejects_empty_cases(tmp_path: Path, monkeypatch):
    settings = DummySettings(tmp_path)
    monkeypatch.setattr(evaluation, "get_settings", lambda: settings)
    app = FastAPI()
    app.include_router(evaluation.router, prefix="/evaluation")

    response = TestClient(app).post(
        "/evaluation/runs",
        json={"base_model": "base", "run_inference": False},
    )

    assert response.status_code == 400
    assert "评估样本为空" in response.json()["detail"]


def test_failed_evaluation_can_retry_idempotently(tmp_path: Path, monkeypatch):
    settings = DummySettings(tmp_path)
    monkeypatch.setattr(evaluation, "get_settings", lambda: settings)
    run_id = "eval_retry"
    path = tmp_path / "outputs" / "evaluations" / f"{run_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "scenario": "qa_assistant",
                "status": "failed",
                "created_at": "2026-06-20T00:00:00",
                "base_model": "base",
                "finetuned_model": "fine",
                "backend": "huggingface",
                "run_inference": False,
                "cases": [
                    {
                        "prompt": "hello",
                        "base_output": "base answer",
                        "finetuned_output": "fine answer",
                    }
                ],
                "inference_options": {
                    "max_tokens": 64,
                    "temperature": 0.2,
                    "max_cases": 20,
                    "auto_merge_adapter": True,
                },
                "reproducibility": {},
                "warnings": [],
            }
        ),
        encoding="utf-8",
    )
    app = FastAPI()
    app.include_router(evaluation.router, prefix="/evaluation")

    response = TestClient(app).post(f"/evaluation/runs/{run_id}/retry")
    assert response.status_code == 200
    completed = TestClient(app).get(f"/evaluation/runs/{run_id}").json()
    assert completed["status"] == "completed"
    assert len(completed["retry_history"]) == 1
    assert completed["cases"][0]["base_output"] == "base answer"


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
    assert payload["env_template"]["FINETUNE_API_BASE_URL"] == "http://127.0.0.1:8010"
    assert payload["inference_target"] == {
        "model_alias": "support-v1",
        "model_path": "qwen2.5:7b",
        "backend": "huggingface",
        "lora_adapter": str(adapter_dir),
    }
    assert "/inference/generate" in payload["openai_compatible_examples"]["python"]


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

    monkeypatch.setattr(deployment, "_find_training_record", lambda _task_id: record)

    def _save_assertion(updated):
        assert updated is record

    monkeypatch.setattr("services.training.records.save_training_record", _save_assertion)

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
    assert record.evaluation_run_id == "eval_history"
    assert record.deployment_package_id == payload["package_id"]
    assert record.promotion_state == "release_draft"


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


def test_deployment_alias_is_visible_only_after_activation(tmp_path: Path, monkeypatch):
    settings = DummySettings(tmp_path)
    monkeypatch.setattr(deployment, "get_settings", lambda: settings)
    adapter_dir = tmp_path / "outputs" / "train_activation" / "adapter"
    adapter_dir.mkdir(parents=True)
    _write_eval_run(
        tmp_path,
        "eval_activation",
        training_task_id="train_activation",
        base_model="base-activation",
        adapter_path=str(adapter_dir),
    )
    app = FastAPI()
    app.include_router(deployment.router, prefix="/deployment")
    client = TestClient(app)

    package = client.post(
        "/deployment/packages",
        json={
            "training_task_id": "train_activation",
            "base_model": "base-activation",
            "adapter_path": str(adapter_dir),
            "evaluation_run_id": "eval_activation",
            "model_alias": "activation-alias",
        },
    ).json()

    assert deployment.resolve_deployed_model("activation-alias") is None
    activated = client.post(f"/deployment/packages/{package['package_id']}/activate")
    assert activated.status_code == 200
    assert activated.json()["status"] == "active"
    assert deployment.resolve_deployed_model("activation-alias") is not None

    delete_active = client.delete(f"/deployment/packages/{package['package_id']}")
    assert delete_active.status_code == 409

    deactivated = client.post(f"/deployment/packages/{package['package_id']}/deactivate")
    assert deactivated.status_code == 200
    assert deployment.resolve_deployed_model("activation-alias") is None


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
            "min_good_rate": 0,
            "min_win_rate": 0,
        },
    )

    assert missing_eval.status_code == 400
    assert failed_gate.status_code == 400
    assert "评估门禁未通过" in failed_gate.json()["detail"]


def test_deployment_rejects_low_score_coverage(tmp_path: Path, monkeypatch):
    settings = DummySettings(tmp_path)
    monkeypatch.setattr(deployment, "get_settings", lambda: settings)
    adapter_dir = tmp_path / "outputs" / "train_coverage" / "adapter"
    adapter_dir.mkdir(parents=True)
    payload = _write_eval_run(
        tmp_path,
        "eval_coverage",
        training_task_id="train_coverage",
        base_model="base-coverage",
        adapter_path=str(adapter_dir),
    )
    payload["metrics"]["human_score_count"] = 1
    (tmp_path / "outputs" / "evaluations" / "eval_coverage.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    app = FastAPI()
    app.include_router(deployment.router, prefix="/deployment")
    response = TestClient(app).post(
        "/deployment/packages",
        json={
            "training_task_id": "train_coverage",
            "base_model": "base-coverage",
            "adapter_path": str(adapter_dir),
            "evaluation_run_id": "eval_coverage",
        },
    )

    assert response.status_code == 400
    assert "评分覆盖率" in response.json()["detail"]


def test_deployment_rejects_incomplete_evaluation_cases(tmp_path: Path, monkeypatch):
    settings = DummySettings(tmp_path)
    monkeypatch.setattr(deployment, "get_settings", lambda: settings)
    adapter_dir = tmp_path / "outputs" / "train_incomplete" / "adapter"
    adapter_dir.mkdir(parents=True)
    payload = _write_eval_run(
        tmp_path,
        "eval_incomplete",
        training_task_id="train_incomplete",
        base_model="base-incomplete",
        adapter_path=str(adapter_dir),
    )
    payload["cases"][0]["finetuned_output"] = None
    (tmp_path / "outputs" / "evaluations" / "eval_incomplete.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    app = FastAPI()
    app.include_router(deployment.router, prefix="/deployment")
    response = TestClient(app).post(
        "/deployment/packages",
        json={
            "training_task_id": "train_incomplete",
            "base_model": "base-incomplete",
            "adapter_path": str(adapter_dir),
            "evaluation_run_id": "eval_incomplete",
        },
    )

    assert response.status_code == 400
    assert "未完成或失败样本" in response.json()["detail"]


def test_full_training_deployment_uses_final_model_directory(tmp_path: Path, monkeypatch):
    settings = DummySettings(tmp_path)
    monkeypatch.setattr(deployment, "get_settings", lambda: settings)
    full_model_dir = tmp_path / "outputs" / "train_full" / "full_model"
    full_model_dir.mkdir(parents=True)
    _write_eval_run(
        tmp_path,
        "eval_full",
        training_task_id="train_full",
        base_model="base-full",
        adapter_path=None,
    )
    eval_path = tmp_path / "outputs" / "evaluations" / "eval_full.json"
    eval_payload = json.loads(eval_path.read_text(encoding="utf-8"))
    eval_payload["finetuned_model"] = str(full_model_dir)
    eval_path.write_text(json.dumps(eval_payload), encoding="utf-8")

    record = TrainingRecord(
        id="train_full",
        model_name="base-full",
        dataset_name="dataset",
        base_model_id="base-full",
        dataset_id="dataset",
        task_goal="qa_assistant",
        method="full",
        status="completed",
        start_time="2026-04-24T00:00:00",
        config={"model_id": "base-full", "dataset_id": "dataset"},
        output_path=str(full_model_dir.parent),
        checkpoint_path=str(full_model_dir),
    )

    monkeypatch.setattr(deployment, "_find_training_record", lambda _task_id: record)
    monkeypatch.setattr("services.training.records.save_training_record", lambda _r: None)
    app = FastAPI()
    app.include_router(deployment.router, prefix="/deployment")
    response = TestClient(app).post(
        "/deployment/packages",
        json={
            "training_task_id": "train_full",
            "evaluation_run_id": "eval_full",
            "model_alias": "full-release",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["adapter_path"] == ""
    assert payload["merged_model_path"] == str(full_model_dir)
    assert payload["inference_target"]["model_path"] == str(full_model_dir)
    assert payload["inference_target"]["lora_adapter"] is None


def test_training_evaluation_deployment_alias_end_to_end(tmp_path: Path, monkeypatch):
    settings = DummySettings(tmp_path)
    monkeypatch.setattr(evaluation, "get_settings", lambda: settings)
    monkeypatch.setattr(deployment, "get_settings", lambda: settings)

    adapter_dir = tmp_path / "outputs" / "train_e2e" / "lora_adapter"
    adapter_dir.mkdir(parents=True)
    snapshot_path = adapter_dir.parent / "evaluation_snapshot.json"
    snapshot_cases = [{"question": f"hello-{index}", "answer": f"expected-{index}"} for index in range(5)]
    snapshot_path.write_text(json.dumps(snapshot_cases), encoding="utf-8")
    from training_engine.reporter import hash_path
    record = TrainingRecord(
        id="train_e2e",
        model_name="base-e2e",
        dataset_name="dataset-e2e",
        base_model_id="base-e2e",
        dataset_id="dataset-e2e",
        task_goal="qa_assistant",
        method="qlora",
        status="completed",
        start_time="2026-04-24T00:00:00",
        config={"model_id": "base-e2e", "dataset_id": "dataset-e2e"},
        output_path=str(adapter_dir.parent),
        adapter_path=str(adapter_dir),
        checkpoint_path=str(adapter_dir),
        release_id="release-e2e",
        evaluation_snapshot_path=str(snapshot_path),
        evaluation_snapshot_hash=hash_path(snapshot_path),
        artifact_digest=hash_path(adapter_dir),
    )

    monkeypatch.setattr(evaluation, "_find_training_record", lambda _task_id: record)
    monkeypatch.setattr("services.training.records.find_training_record", lambda _task_id: record)

    def _save_assertion(updated):
        assert updated is record

    monkeypatch.setattr("services.training.records.save_training_record", _save_assertion)

    async def fake_inference(**kwargs):
        prompts = kwargs["prompts"]
        prefix = "fine" if kwargs.get("lora_adapter") else "base"
        return [f"{prefix}:{prompt}" for prompt in prompts]

    monkeypatch.setattr(evaluation, "run_model_inference_batch_with_retry", fake_inference)

    app = FastAPI()
    app.include_router(evaluation.router, prefix="/evaluation")
    app.include_router(deployment.router, prefix="/deployment")
    client = TestClient(app)

    evaluation_response = client.post(
        "/evaluation/runs",
        json={
            "training_task_id": "train_e2e",
            "base_model": "base-e2e",
            "backend": "huggingface",
        },
    )
    assert evaluation_response.status_code == 200
    run_id = evaluation_response.json()["run_id"]

    completed = client.get(f"/evaluation/runs/{run_id}").json()
    assert completed["status"] == "completed"
    assert completed["base_outputs"] == [f"base:hello-{index}" for index in range(5)]
    assert completed["finetuned_outputs"] == [f"fine:hello-{index}" for index in range(5)]
    assert record.evaluation_run_id == run_id
    assert record.promotion_state == "evaluated"

    for case_index in range(5):
        scored = client.post(
            f"/evaluation/runs/{run_id}/score",
            json={"case_index": case_index, "score": "good"},
        )
        assert scored.status_code == 200
    assert scored.json()["metrics"]["good_rate"] == 1.0

    deployment_response = client.post(
        "/deployment/packages",
        json={
            "training_task_id": "train_e2e",
            "evaluation_run_id": run_id,
            "model_alias": "release-e2e-alias",
        },
    )
    assert deployment_response.status_code == 200
    package = deployment_response.json()
    assert package["evaluation_gate"]["passed"] is True
    assert package["status"] == "draft"
    assert record.deployment_package_id == package["package_id"]
    assert record.promotion_state == "release_draft"

    activated = client.post(f"/deployment/packages/{package['package_id']}/activate")
    assert activated.status_code == 200
    assert record.promotion_state == "active"
    resolved = deployment.resolve_deployed_model("release-e2e-alias")
    assert resolved == {
        "package_id": package["package_id"],
        "model_alias": "release-e2e-alias",
        "model_path": "base-e2e",
        "backend": "huggingface",
        "lora_adapter": str(adapter_dir),
    }
