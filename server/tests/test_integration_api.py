"""
Integration tests for backend API flows.

These tests exercise multi-module interactions between API endpoints,
using FastAPI TestClient to validate request/response contracts across
the full application stack (routing, middleware, business logic).
"""
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app

client = TestClient(app)

pytestmark = pytest.mark.integration


class TestHealthAndDeviceFlow:
    """Integration: health -> device info -> VRAM flow."""

    def test_health_then_device_info(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        health = resp.json()
        assert health.get("status") in ("ok", "healthy")

        resp = client.get("/device/info")
        assert resp.status_code == 200
        device = resp.json()
        assert "cuda_available" in device
        assert "memory" in device

    def test_device_vram_endpoint(self):
        resp = client.get("/device/vram")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)


class TestModelDatasetListFlow:
    """Integration: list models -> list datasets -> verify API contract."""

    def test_list_models_and_datasets(self):
        models_resp = client.get("/models/list")
        assert models_resp.status_code == 200
        assert isinstance(models_resp.json(), list)

        datasets_resp = client.get("/datasets/list")
        assert datasets_resp.status_code == 200
        assert isinstance(datasets_resp.json(), list)

    def test_model_center_suggestions(self):
        resp = client.get("/model-center/suggestions")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, (list, dict))
        if isinstance(data, list):
            for item in data:
                assert "name" in item or "id" in item or "model_id" in item, (
                    f"suggestion item missing identifier: {item}"
                )

    def test_model_center_local_models(self):
        resp = client.get("/model-center/local")
        assert resp.status_code == 200


class TestTrainingStatusFlow:
    """Integration: training status endpoint contract."""

    def test_training_status_response(self):
        resp = client.get("/training/status")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)
        assert "tasks" in data or "status" in data, f"unexpected shape: {list(data.keys())}"


class TestChatSessionFlow:
    """Integration: create session -> list sessions -> delete session."""

    def test_create_and_list_sessions(self):
        resp = client.get("/chat/sessions")
        assert resp.status_code == 200

        create_resp = client.post("/chat/sessions", json={"title": "integration-test"})
        assert create_resp.status_code in (200, 201)
        session = create_resp.json()

        session_id = session.get("id") or session.get("session_id")
        if session_id:
            detail_resp = client.get(f"/chat/sessions/{session_id}")
            assert detail_resp.status_code == 200
            client.delete(f"/chat/sessions/{session_id}")


class TestEvaluationAndDeploymentFlow:
    """Integration: evaluation runs -> deployment packages API contract."""

    def test_evaluation_runs_list(self):
        resp = client.get("/evaluation/runs")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, (list, dict)), f"expected list/dict, got {type(data).__name__}"

    def test_deployment_packages_list(self):
        resp = client.get("/deployment/packages")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, (list, dict)), f"expected list/dict, got {type(data).__name__}"


class TestInferenceFlow:
    """Integration: inference backends status -> performance info."""

    def test_inference_backends(self):
        resp = client.get("/inference/backends")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, (list, dict))

    def test_inference_performance(self):
        resp = client.get("/inference/performance")
        assert resp.status_code == 200


class TestWorkflowEndpoints:
    """Integration: workflow runtime and observability."""

    def test_workflow_list(self):
        resp = client.get("/workflows")
        assert resp.status_code == 200

    def test_workflow_observability_not_found(self):
        resp = client.get("/workflows/nonexistent-workflow-id/observability")
        assert resp.status_code in (404, 200)


class TestContextEndpoints:
    """Integration: context scanning and retrieval."""

    def test_context_scan(self):
        resp = client.post("/context/scan", json={"path": "."})
        assert resp.status_code == 200, f"scan failed: {resp.text}"
        data = resp.json()
        assert isinstance(data, dict)

    def test_context_index_status(self):
        resp = client.get("/context/index")
        assert resp.status_code == 200


class TestGatewayAndHeartbeat:
    """Integration: gateway status and heartbeat endpoints."""

    def test_gateway_status(self):
        resp = client.get("/gateway/status")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)

    def test_heartbeat_status(self):
        resp = client.get("/heartbeat/status")
        assert resp.status_code == 200, f"heartbeat/status returned {resp.status_code}"


class TestKnowledgeBaseFlow:
    """Integration: knowledge base collection listing."""

    def test_knowledge_collections(self):
        resp = client.get("/knowledge/collections")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, (list, dict))

    def test_knowledge_embedder_status(self):
        resp = client.get("/knowledge/embedder/status")
        assert resp.status_code == 200