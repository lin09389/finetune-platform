from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from .nodes import AgentSessionLangGraphRuntime
from .state import AgentSessionGraphState


def _after_model(state: AgentSessionGraphState) -> str:
    if state.get("pending_tool_calls"):
        return "tool_exec"
    return "finalize"


def _after_tool_exec(state: AgentSessionGraphState) -> str:
    execution_state = str(state.get("execution_state") or "")
    if execution_state == "waiting_permission":
        return "permission_gate"
    if execution_state == "waiting_approval":
        return "action_gate"
    if execution_state == "approved_for_execution":
        return "action_exec"
    if execution_state in {"completed", "failed", "needs_manual_review"}:
        return "finalize"
    return "model_call"


def _after_permission(state: AgentSessionGraphState) -> str:
    execution_state = str(state.get("execution_state") or "")
    if execution_state in {"failed", "needs_manual_review", "completed"}:
        return "finalize"
    return "model_call"


def _after_action(state: AgentSessionGraphState) -> str:
    execution_state = str(state.get("execution_state") or "")
    if execution_state in {"failed", "needs_manual_review", "completed"}:
        return "finalize"
    if execution_state == "waiting_approval":
        return "action_gate"
    return "model_call"


def build_agent_session_graph(*, repository, processor, model_call=None, checkpointer=None, runtime=None):
    runtime = runtime or AgentSessionLangGraphRuntime(repository=repository, processor=processor, model_call=model_call)
    graph = StateGraph(AgentSessionGraphState)
    graph.add_node("bootstrap", runtime.bootstrap_node)
    graph.add_node("plan", runtime.plan_node)
    graph.add_node("model_call", runtime.model_call_node)
    graph.add_node("tool_exec", runtime.tool_exec_node)
    graph.add_node("permission_gate", runtime.permission_gate_node)
    graph.add_node("action_gate", runtime.action_gate_node)
    graph.add_node("action_exec", runtime.action_exec_node)
    graph.add_node("finalize", runtime.finalize_node)
    graph.add_edge(START, "bootstrap")
    graph.add_edge("bootstrap", "plan")
    graph.add_edge("plan", "model_call")
    graph.add_conditional_edges("model_call", _after_model, {"tool_exec": "tool_exec", "finalize": "finalize"})
    graph.add_conditional_edges(
        "tool_exec",
        _after_tool_exec,
        {
            "permission_gate": "permission_gate",
            "action_gate": "action_gate",
            "action_exec": "action_exec",
            "model_call": "model_call",
            "finalize": "finalize",
        },
    )
    graph.add_conditional_edges(
        "permission_gate",
        _after_permission,
        {"model_call": "model_call", "finalize": "finalize"},
    )
    graph.add_conditional_edges(
        "action_gate",
        _after_action,
        {"model_call": "model_call", "action_gate": "action_gate", "finalize": "finalize"},
    )
    graph.add_edge("action_exec", "model_call")
    graph.add_edge("finalize", END)
    if checkpointer is None:
        return graph.compile()
    return graph.compile(checkpointer=checkpointer)
