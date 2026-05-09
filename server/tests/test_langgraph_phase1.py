"""Phase 1 LangGraph migration smoke tests."""

from __future__ import annotations

import pytest

from agent_runtime.langgraph.graph_builder import build_workflow_graph
from agent_runtime.langgraph.langgraph_tools import execute_legacy_tool, parse_tool_payload
from agent_runtime.langgraph.nodes import execute_tool_bridge_node
from agent_runtime.langgraph.state import WorkflowState
from agent_runtime.tool_models import AgentToolRequest


class DummyExecutor:
    def execute(self, request, *, workflow_id, step_id, agent_id, project, permission_rules=None, replay_of_call_id=None):
        return type("Result", (), {"model_dump_json": lambda self, ensure_ascii=False: '{"tool":"%s","status":"completed"}' % request.tool})()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_parse_tool_payload_round_trip():
    request = parse_tool_payload('{"tool":"list_files","arguments":{"pattern":"**/*.py"}}')
    assert isinstance(request, AgentToolRequest)
    assert request.tool == "list_files"
    assert request.arguments["pattern"] == "**/*.py"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_legacy_tool_bridge():
    executor = DummyExecutor()
    result = execute_legacy_tool(
        executor,
        '{"tool":"finalize","arguments":{"summary":"done"}}',
        workflow_id="wf_1",
        step_id="step_1",
        agent_id="planner",
        project={},
    )
    assert '"tool":"finalize"' in result


@pytest.mark.asyncio
async def test_execute_tool_bridge_node_clears_payload():
    state: WorkflowState = {
        "workflow_id": "wf_1",
        "messages": [],
        "current_agent_id": "planner",
        "metadata": {
            "bridge_payload": '{"tool":"list_files","arguments":{"pattern":"**/*"}}',
            "tool_executor": DummyExecutor(),
            "project": {},
            "step_id": "step_1",
            "primary_agent_id": "planner",
        },
    }
    update = await execute_tool_bridge_node(state)
    assert update["metadata"]["bridge_status"] == "completed"
    assert update["metadata"]["bridge_payload"] is None
    assert update["messages"][-1]["role"] == "tool"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_build_workflow_graph_compiles():
    graph = await build_workflow_graph(use_checkpointer=False)
    assert graph is not None
