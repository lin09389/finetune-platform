"""Graph builder for the LangGraph-based workflow runtime."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from .checkpoint import get_checkpointer
from .nodes import bootstrap_node, curate_memory_node, execute_tool_bridge_node, implement_node, plan_node, review_node
from .state import WorkflowState


def _route_after_bootstrap(_: WorkflowState) -> str:
    return "plan"


def _route_after_plan(state: WorkflowState) -> str:
    if state.get("metadata", {}).get("bridge_payload"):
        return "tool_bridge"
    return "implement"


def _route_after_implement(state: WorkflowState) -> str:
    if state.get("metadata", {}).get("bridge_payload"):
        return "tool_bridge"
    return "review"


def _route_after_review(state: WorkflowState) -> str:
    if state.get("needs_manual_review"):
        return "end"
    return "curate_memory"


def _route_after_tool_bridge(_: WorkflowState) -> str:
    return "review"


async def build_workflow_graph(use_checkpointer: bool = True):
    """Build the Phase 1 workflow graph."""
    builder = StateGraph(WorkflowState)
    builder.add_node("bootstrap", bootstrap_node)
    builder.add_node("plan", plan_node)
    builder.add_node("implement", implement_node)
    builder.add_node("tool_bridge", execute_tool_bridge_node)
    builder.add_node("review", review_node)
    builder.add_node("curate_memory", curate_memory_node)
    builder.add_edge(START, "bootstrap")
    builder.add_conditional_edges("bootstrap", _route_after_bootstrap, {"plan": "plan"})
    builder.add_conditional_edges("plan", _route_after_plan, {"tool_bridge": "tool_bridge", "implement": "implement"})
    builder.add_conditional_edges("implement", _route_after_implement, {"tool_bridge": "tool_bridge", "review": "review"})
    builder.add_conditional_edges("tool_bridge", _route_after_tool_bridge, {"review": "review"})
    builder.add_conditional_edges("review", _route_after_review, {"curate_memory": "curate_memory", "end": END})
    builder.add_edge("curate_memory", END)
    if use_checkpointer:
        return builder.compile(checkpointer=await get_checkpointer())
    return builder.compile()
