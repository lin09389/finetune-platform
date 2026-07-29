import asyncio
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api import evaluation


class DummySettings:
    def __init__(self, root: Path):
        self.outputs_dir_resolved = root / "outputs"
        self.datasets_dir_resolved = root / "datasets"

@pytest.fixture
def test_app(tmp_path: Path, monkeypatch):
    settings = DummySettings(tmp_path)
    monkeypatch.setattr(evaluation, "get_settings", lambda: settings)

    app = FastAPI()
    app.include_router(evaluation.router, prefix="/evaluation")
    return app

@pytest.mark.asyncio
async def test_sse_stream_receives_updates_incrementally(test_app, tmp_path: Path):
    run_id = "test_run_123"
    path = tmp_path / "outputs" / "evaluations" / f"{run_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "run_id": run_id,
        "status": "running",
        "cases": []
    }
    await evaluation._write_run_payload(run_id, payload)

    async def simulate_background_flush():
        await asyncio.sleep(0.5)
        for i in range(1, 4):
            payload["cases"].append({"case_index": i, "base_output": f"out_{i}"})
            if i == 3:
                payload["status"] = "completed"
            async with evaluation._get_run_lock(run_id):
                await evaluation._write_run_payload(run_id, payload)
            if run_id in evaluation._run_events:
                evaluation._run_events[run_id].set()
            await asyncio.sleep(0.5)

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        bg_task = asyncio.create_task(simulate_background_flush())

        events = []
        async with client.stream("GET", f"/evaluation/runs/{run_id}/stream") as response:
            assert response.status_code == 200
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = json.loads(line[6:])
                    events.append(data)
                    if data.get("status") == "completed":
                        break

        await bg_task

        assert len(events) >= 3
        assert len(events[-1]["cases"]) == 3
        assert events[-1]["status"] == "completed"

@pytest.mark.asyncio
async def test_standalone_judge_workflow(test_app, tmp_path: Path, monkeypatch):
    run_id = "test_run_456"
    path = tmp_path / "outputs" / "evaluations" / f"{run_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "run_id": run_id,
        "scenario": "qa_assistant",
        "status": "completed",
        "cases": [
            {
                "prompt": "Hello",
                "base_output": "Hi",
                "finetuned_output": "Hello world",
                "human_score": {
                    "case_index": 0,
                    "score": "bad",
                    "notes": "LLM Auto Evaluated"
                }
            }
        ]
    }
    await evaluation._write_run_payload(run_id, payload)

    async def mock_run_model_inference_batch_with_retry(*args, **kwargs):
        # Select the fine-tuned answer in the deterministic blind A/B ordering.
        prompts = kwargs.get("prompts")
        import hashlib

        swapped = hashlib.sha256(b"Hello").digest()[0] % 2 == 1
        winner = "a" if swapped else "b"
        return [json.dumps({"winner": winner, "reason": "better"})] * len(prompts)

    monkeypatch.setattr(evaluation, "run_model_inference_batch_with_retry", mock_run_model_inference_batch_with_retry)

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(f"/evaluation/runs/{run_id}/judge", json={"judge_model": "gpt-4"})
        assert resp.status_code == 200

        # Poll till status complete
        for _ in range(50):
            resp = await client.get(f"/evaluation/runs/{run_id}")
            data = resp.json()
            if data["status"] == "completed":
                assert data["cases"][0]["human_score"]["score"] == "good"
                assert data["cases"][0]["human_score"]["notes"] == "LLM Auto Evaluated"
                assert data["cases"][0]["human_score"]["source"] == "llm_judge"
                break
            await asyncio.sleep(0.1)
        else:
            pytest.fail("Judge task did not complete in time")
