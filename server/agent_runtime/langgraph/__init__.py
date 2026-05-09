"""
LangGraph-based workflow engine for the finetune-platform.

This module replaces the legacy agent_runtime engine, tool_loop, and runner
with a StateGraph-based orchestration layer built on LangGraph.

Migration map:
  - engine.py → StateGraph in graph_builder.py
  - tool_loop.py → ReAct pattern with ToolNode in nodes.py
  - runner.py → ChatModel.bind_tools() in nodes.py
  - actions.py approval gates → interrupt() + Command(resume=...)
  - repository.py state persistence → AsyncSqliteSaver checkpointer
  - execution_state.py → WorkflowState.state field in state.py

API compatibility:
  All existing REST endpoints are preserved. Internal implementations
  delegate to LangGraph graphs. Only one new endpoint is added:
    POST /workflows/{workflow_id}/resume  (replaces step/action approval)

Frontend SSE streams adapt from astream_events() output to existing
event_type format.
"""