"""
AI 对话系统集成测试

测试覆盖：
- API 端点集成
- 数据流完整性
- 前后端交互
"""
import os
import sys
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app
from rag.vector_store import reset_vector_store

pytestmark = pytest.mark.usefixtures("inference_in_process")


class TestDialogueAPIIntegration:
    """对话 API 集成测试"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_health_check(self, client):
        """测试健康检查端点"""
        response = client.get("/health")
        assert response.status_code == 200

    def test_chat_session_create(self, client):
        """测试创建聊天会话"""
        response = client.post(
            "/chat/sessions",
            json={
                "title": "Test Session",
                "metadata": {"model_id": "test_model"}
            }
        )
        assert response.status_code in [200, 201]
        data = response.json()
        assert "id" in data or "session_id" in data

    def test_chat_session_list(self, client):
        """测试获取会话列表"""
        response = client.get("/chat/sessions")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list) or "sessions" in data

    def test_chat_session_get(self, client):
        """测试获取单个会话"""
        response = client.get("/chat/sessions/nonexistent_session")
        assert response.status_code in [200, 404]

    def test_chat_session_delete(self, client):
        """测试删除会话"""
        response = client.delete("/chat/sessions/nonexistent_session")
        assert response.status_code in [200, 404]

    def test_chat_messages_add(self, client):
        """测试添加消息"""
        session_response = client.post(
            "/chat/sessions",
            json={"title": "Message Test Session"},
        )
        if session_response.status_code not in [200, 201]:
            pytest.skip("Session creation unavailable")

        session_data = session_response.json()
        session_id = session_data.get("id") or session_data.get("session_id")
        if not session_id:
            pytest.skip("Session id missing in response")

        response = client.post(
            f"/chat/sessions/{session_id}/messages",
            json={
                "role": "user",
                "content": "Hello",
                "metadata": {"timestamp": datetime.now().isoformat()},
            }
        )
        assert response.status_code == 200

    def test_inference_backends_list(self, client):
        """测试获取推理后端列表"""
        response = client.get("/inference/backends")
        assert response.status_code == 200
        data = response.json()
        assert "backends" in data or isinstance(data, list)

    def test_inference_models_list(self, client):
        """测试获取推理模型列表"""
        response = client.get("/inference/models")
        assert response.status_code == 200

    def test_device_info(self, client):
        """测试设备信息端点"""
        response = client.get("/device/info")
        assert response.status_code == 200
        data = response.json()
        assert "platform" in data or "device_name" in data

    def test_models_list(self, client):
        """测试模型列表端点"""
        response = client.get("/models")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list) or "models" in data

    def test_datasets_list(self, client):
        """测试数据集列表端点"""
        response = client.get("/datasets")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list) or "datasets" in data


class TestContextAPIIntegration:
    """上下文 API 集成测试"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_context_scan(self, client):
        """测试项目上下文扫描"""
        response = client.post("/context/scan", json={"path": "."})
        assert response.status_code in [200, 400, 404]

    def test_context_index(self, client):
        """测试上下文索引"""
        response = client.post("/context/index", json={"path": "."})
        assert response.status_code in [200, 400, 404]

    def test_context_retrieve(self, client):
        """测试上下文检索"""
        response = client.post(
            "/context/retrieve",
            json={"query": "test query", "top_k": 5}
        )
        assert response.status_code in [200, 400, 404]


class TestKnowledgeAPIIntegration:
    """知识库 API 集成测试"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_knowledge_collections_list(self, client):
        """测试知识库集合列表"""
        response = client.get("/knowledge/collections")
        assert response.status_code == 200
        data = response.json()
        assert "collections" in data or isinstance(data, list)

    def test_knowledge_query(self, client):
        """测试知识库查询"""
        response = client.post(
            "/knowledge/query",
            json={"query": "test query", "collection": "default", "top_k": 5}
        )
        assert response.status_code in [200, 400, 404]


class TestSkillsAPIIntegration:
    """技能 API 集成测试"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_skills_list(self, client):
        """测试技能列表"""
        response = client.get("/skills")
        assert response.status_code == 404

    def test_skill_memory_configs(self, client):
        """测试技能记忆配置"""
        response = client.get("/skills/memory/configs")
        assert response.status_code == 404

    def test_skill_memory_preferences(self, client):
        """测试用户偏好"""
        response = client.get("/skills/memory/preferences")
        assert response.status_code == 404

    def test_skill_memory_history(self, client):
        """测试操作历史"""
        response = client.get("/skills/memory/history")
        assert response.status_code == 404


class TestAgentAPIIntegration:
    """Agent API 集成测试"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_agent_capabilities(self, client):
        """测试 Agent 能力列表"""
        response = client.get("/agent/capabilities")
        assert response.status_code == 404

    def test_agent_detect_intent(self, client):
        """测试意图检测"""
        response = client.post(
            "/agent/detect-intent",
            json={"message": "帮我截图"}
        )
        assert response.status_code == 404

    def test_agent_audit_stats(self, client):
        """测试审计统计"""
        response = client.get("/agent/audit/stats")
        assert response.status_code == 404

    def test_agent_audit_recent(self, client):
        """测试最近审计日志"""
        response = client.get("/agent/audit/recent")
        assert response.status_code == 404


class TestCUAAPIIntegration:
    """CUA API 集成测试"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_cua_screen_info(self, client):
        """测试屏幕信息"""
        response = client.get("/cua/screen/info")
        assert response.status_code in [200, 404, 501]

    def test_cua_safety_status(self, client):
        """测试安全状态"""
        response = client.get("/cua/safety/status")
        assert response.status_code in [200, 404, 501]

    def test_cua_mouse_position(self, client):
        """测试鼠标位置"""
        response = client.get("/cua/mouse/position")
        assert response.status_code in [200, 404, 501]

    def test_cua_window_list(self, client):
        """测试窗口列表"""
        response = client.get("/cua/window/list")
        assert response.status_code in [200, 404, 501]


class TestMCPAPIIntegration:
    """MCP API 集成测试"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_mcp_tools_list(self, client):
        """测试 MCP 工具列表"""
        response = client.get("/mcp/tools")
        assert response.status_code == 200

    def test_mcp_servers_list(self, client):
        """测试 MCP 服务器列表"""
        response = client.get("/mcp/servers")
        assert response.status_code == 200

    def test_mcp_status(self, client):
        """测试 MCP 状态"""
        response = client.get("/mcp/status")
        assert response.status_code == 200
        data = response.json()
        assert data["tier"] == "experimental"
        assert data["available"] is True
        assert data["failure_mode"] == "explicit_status"
        assert "dependency_status" in data
        assert "runtime_status" in data
        assert "message" in data


class TestHeartbeatAPIIntegration:
    """Heartbeat API 集成测试"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_heartbeat_status(self, client):
        """测试 Heartbeat 状态"""
        response = client.get("/heartbeat/status")
        assert response.status_code == 200
        data = response.json()
        assert data["tier"] == "experimental"
        assert data["available"] is True
        assert data["failure_mode"] == "explicit_status"
        assert "dependency_status" in data
        assert "runtime_status" in data
        assert "message" in data
        assert "scheduler" in data
        assert "executor" in data


class TestWorkspaceAPIIntegration:
    """工作空间 API 集成测试"""

    @pytest.fixture
    def client(self, tmp_path):
        reset_vector_store(str(tmp_path / "vectors"))
        return TestClient(app)

    def test_workspace_list(self, client):
        """测试工作空间列表"""
        response = client.get("/workspace/workspaces")
        assert response.status_code == 200

    def test_workspace_create(self, client):
        """测试创建工作空间"""
        response = client.post(
            "/workspace/workspaces",
            json={"name": "Test Workspace", "description": "Test"}
        )
        assert response.status_code in [200, 201]

    def test_workspace_projects_list(self, client):
        """测试项目列表"""
        response = client.get("/workspace/projects")
        assert response.status_code == 200

    def test_workspace_tasks_list(self, client):
        """测试任务列表"""
        response = client.get("/workspace/tasks")
        assert response.status_code == 200


class TestInferencePerformanceIntegration:
    """推理性能集成测试"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_inference_performance_stats(self, client):
        """测试性能统计"""
        response = client.get("/inference/performance")
        assert response.status_code == 200

    def test_inference_performance_recommendations(self, client):
        """测试性能建议"""
        response = client.get("/inference/performance/recommendations")
        assert response.status_code == 200

    def test_inference_performance_clear(self, client):
        """测试清空性能历史"""
        response = client.post("/inference/performance/clear")
        assert response.status_code == 200


class TestEndToEndFlow:
    """端到端流程测试"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_chat_flow(self, client):
        """测试完整聊天流程"""
        session_response = client.post(
            "/chat/sessions",
            json={"title": "E2E Test Session"}
        )
        assert session_response.status_code in [200, 201]

        session_data = session_response.json()
        session_id = session_data.get("id") or session_data.get("session_id")

        if session_id:
            get_response = client.get(f"/chat/sessions/{session_id}")
            assert get_response.status_code == 200

            delete_response = client.delete(f"/chat/sessions/{session_id}")
            assert delete_response.status_code in [200, 404]

    def test_model_management_flow(self, client):
        """测试模型管理流程"""
        list_response = client.get("/models")
        assert list_response.status_code == 200

        data = list_response.json()
        models = data if isinstance(data, list) else data.get("models", [])

        assert isinstance(models, list)

    def test_dataset_management_flow(self, client):
        """测试数据集管理流程"""
        list_response = client.get("/datasets")
        assert list_response.status_code == 200

        data = list_response.json()
        datasets = data if isinstance(data, list) else data.get("datasets", [])

        assert isinstance(datasets, list)

