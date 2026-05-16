"""Graph builder for the LangGraph-based workflow runtime."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from .checkpoint import get_checkpointer
from .nodes import LangGraphWorkflowRuntime
from .state import WorkflowState


def _route_after_bootstrap(_: WorkflowState) -> str:
    return "model_call"


def _route_after_model_call(state: WorkflowState) -> str:
    if state.get("pending_tool_calls"):
        return "tool_exec"
    return "review_gate"


def _route_after_tool_exec(state: WorkflowState) -> str:
    if state.get("pending_actions"):
        return "action_gate"
    if state.get("final_output"):
        return "review_gate"
    return "model_call"


def _route_after_action_gate(state: WorkflowState) -> str:
    if state.get("pending_actions"):
        return "action_gate"
    if state.get("final_output"):
        return "review_gate"
    return "model_call"


def _route_after_review_gate(state: WorkflowState) -> str:
    if state.get("execution_state") == "completed":
        return "curate_memory"
    if state.get("execution_state") == "failed":
        return "end"
    return "bootstrap"


async def build_workflow_graph(
    *,
    repository=None,
    runner=None,
    context_builder=None,
    memory_curator=None,
    action_service=None,
    use_checkpointer: bool = True,
):
    """Build the native LangGraph workflow graph."""
    runtime = LangGraphWorkflowRuntime(
        repository=repository,
        runner=runner,
        context_builder=context_builder,
        memory_curator=memory_curator,
        action_service=action_service,
    )
    builder = StateGraph(WorkflowState)
    builder.add_node("bootstrap", runtime.bootstrap_node)
    builder.add_node("model_call", runtime.model_call_node)
    builder.add_node("tool_exec", runtime.tool_exec_node)
    builder.add_node("action_gate", runtime.action_gate_node)
    builder.add_node("review_gate", runtime.review_gate_node)
    builder.add_node("curate_memory", runtime.curate_memory_node)
    builder.add_edge(START, "bootstrap")
    builder.add_conditional_edges("bootstrap", _route_after_bootstrap, {"model_call": "model_call"})
    builder.add_conditional_edges("model_call", _route_after_model_call, {"tool_exec": "tool_exec", "review_gate": "review_gate"})
    builder.add_conditional_edges(
        "tool_exec",
        _route_after_tool_exec,
        {"action_gate": "action_gate", "review_gate": "review_gate", "model_call": "model_call"},
    )
    builder.add_conditional_edges(
        "action_gate",
        _route_after_action_gate,
        {"action_gate": "action_gate", "review_gate": "review_gate", "model_call": "model_call"},
    )
    builder.add_conditional_edges("review_gate", _route_after_review_gate, {"bootstrap": "bootstrap", "curate_memory": "curate_memory", "end": END})
    builder.add_edge("curate_memory", END)
    if use_checkpointer:
        return builder.compile(checkpointer=await get_checkpointer())
    return builder.compile()
