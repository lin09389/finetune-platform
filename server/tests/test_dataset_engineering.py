from __future__ import annotations

import importlib
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

datasets_api = importlib.import_module("api.datasets")


def _client(tmp_path: Path) -> TestClient:
    datasets_api._datasets_dir = tmp_path
    app = FastAPI()
    app.include_router(datasets_api.router, prefix="/datasets")
    return TestClient(app)


def _write_dataset(root: Path, dataset_id: str, rows: list[dict]) -> None:
    dataset_dir = root / dataset_id
    dataset_dir.mkdir()
    with open(dataset_dir / "data.jsonl", "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def test_analyze_detects_structured_extraction(tmp_path: Path):
    _write_dataset(
        tmp_path,
        "extract",
        [
            {
                "input": "订单金额 19.9 元",
                "schema": {"amount": "number"},
                "output": {"amount": 19.9},
            }
        ],
    )
    response = _client(tmp_path).post(
        "/datasets/analyze",
        json={"dataset_id": "extract", "target_goal": "structured_extraction"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["detected_format"] == "structured_extraction"
    assert payload["valid_count"] == 1
    assert payload["recommended_target_format"] == "input_schema_output_jsonl"
    assert payload["health"]["field_completeness"] == 1.0


def test_transform_and_split_dataset(tmp_path: Path):
    _write_dataset(
        tmp_path,
        "faq",
        [
            {"question": "退款多久到？", "answer": "通常 1-3 个工作日。"},
            {"question": "怎么开发票？", "answer": "在订单详情申请。"},
        ],
    )
    client = _client(tmp_path)

    transform = client.post(
        "/datasets/faq/transform",
        json={"target_format": "openai_messages", "task_goal": "qa_assistant"},
    )
    assert transform.status_code == 200
    assert transform.json()["sample_count"] == 2

    split = client.post(
        "/datasets/faq/split",
        json={"train_ratio": 0.5, "validation_ratio": 0.25, "test_ratio": 0.25, "seed": 1},
    )
    assert split.status_code == 200
    assert sum(item["sample_count"] for item in split.json()["splits"].values()) == 2
