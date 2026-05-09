"""Node implementations for the LangGraph workflow runtime."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from time import perf_counter
from typing import Any

from digital_team.models import TaskStatus
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.types import interrupt

from ..definitions import RuntimeExecutionContext
from ..runner import parse_agent_output
from ..tool_models import AgentToolRequest
from .langgraph_tools import execute_legacy_tool
from .provider_adapter import get_chat_model
from .state import WorkflowState

logger = logging.getLogger(__name__)


def _json_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False)


class LangGraphWorkflowRuntime:
    """Dependency-backed node runtime used by the LangGraph workflow graph."""

    def __init__(self, repository: Any, runner: Any, context_builder: Any, memory_curator: Any, action_service: Any):
        self.repository = repository
        self.runner = runner
        self.context_builder = context_builder
        self.memory_curator = memory_curator
        self.action_service = action_service

    async def bootstrap_node(self, state: WorkflowState) -> dict[str, Any]:
        step = self._current_step(state)
        project = self._project(state)
        if step is None:
            return {"execution_state": "completed"}

        task = self._ensure_task(project, state, step)
        metadata = dict(state.get("metadata") or {})
        metadata["step_started_at"] = metadata.get("step_started_at") or datetime.now().isoformat()
        metadata["project"] = self.repository.get_project(project["id"]) or project
        metadata["active_agent_id"] = step["agent_id"]
        self.repository.update_project(
            project["id"],
            status="running",
            current_stage=step["step_key"],
            metadata={**(project.get("metadata") or {}), "active_agent_id": step["agent_id"], "blocked_state": None},
        )

        if not state.get("messages"):
            messages = self._build_step_messages(project, state, step, task)
        else:
            messages = state.get("messages")

        return {
            "messages": messages,
            "current_step": step["step_key"],
            "current_agent_id": step["agent_id"],
            "current_task_id": task["id"],
            "execution_state": "planning" if state.get("step_index", 0) == 0 else "inspecting",
            "metadata": metadata,
            "approval_required": bool(step.get("requires_approval")),
            "review_required": bool(step.get("requires_approval")),
            "pending_tool_calls": [],
            "pending_actions": [],
            "interrupt_kind": None,
            "interrupt_payload": None,
            "final_output": None,
        }

    async def model_call_node(self, state: WorkflowState) -> dict[str, Any]:
        step = self._current_step(state)
        if step is None:
            return {"execution_state": "completed"}

        project = self._project(state)
        task = self._current_task(state) or self._ensure_task(project, state, step)
        context = self._context_for_step(project, state, step, task)
        model = get_chat_model(context).bind_tools(self._tool_schemas())
        response = await model.ainvoke(state.get("messages") or [])
        ai_message = response if isinstance(response, AIMessage) else AIMessage(content=str(response))

        final_output = None
        if not ai_message.tool_calls and str(ai_message.content or "").strip():
            final_output = parse_agent_output(str(ai_message.content)).model_dump()

        return {
            "messages": [ai_message],
            "pending_tool_calls": list(ai_message.tool_calls or []),
            "execution_state": "verifying" if ai_message.tool_calls else "waiting_approval",
            "final_output": final_output,
        }

    async def tool_exec_node(self, state: WorkflowState) -> dict[str, Any]:
        step = self._current_step(state)
        project = self._project(state)
        task = self._current_task(state)
        if step is None or task is None:
            return {"pending_tool_calls": []}

        metadata = dict(state.get("metadata") or {})
        executor = self.runner.executor if hasattr(self.runner, "executor") else None
        if executor is None:
            from ..tools import AgentToolExecutor

            executor = AgentToolExecutor(self.repository, self.action_service)

        tool_messages: list[ToolMessage] = []
        results = list(state.get("tool_results") or [])
        pending_actions = list(state.get("pending_actions") or [])
        final_output = state.get("final_output")

        for call in state.get("pending_tool_calls") or []:
            tool_name = str(call.get("name") or "tool")
            arguments = call.get("args") if isinstance(call.get("args"), dict) else {}
            started_at = datetime.now().isoformat()
            start_perf = perf_counter()
            tool_call = self.repository.add_tool_call(
                workflow_id=project["id"],
                step_id=task["id"],
                agent_id=step["agent_id"],
                tool_name=tool_name,
                arguments=arguments,
                status="running",
                started_at=started_at,
            )
            self.repository.add_event(
                project["id"],
                task["id"],
                "tool_call_started",
                step["agent_id"],
                f"开始执行工具：{tool_name}",
                {"tool_call_id": tool_call["id"], "tool_name": tool_name, "arguments": arguments},
            )
            try:
                result = executor.execute(
                    AgentToolRequest(tool=tool_name, arguments=arguments),
                    workflow_id=project["id"],
                    step_id=task["id"],
                    agent_id=step["agent_id"],
                    project=project,
                )
                payload = result.model_dump()
                results.append(payload)
                duration_ms = int((perf_counter() - start_perf) * 1000)
                self.repository.update_tool_call(
                    tool_call["id"],
                    status=result.status,
                    result_summary=result.summary,
                    result_payload=result.payload,
                    error=result.error,
                    completed_at=datetime.now().isoformat(),
                    duration_ms=duration_ms,
                )
                self.repository.add_event(
                    project["id"],
                    task["id"],
                    "tool_call_completed" if result.status == "completed" else "tool_call_failed",
                    step["agent_id"],
                    result.summary or f"工具 {tool_name} 已返回",
                    {"tool_call_id": tool_call["id"], "tool_name": tool_name, "status": result.status},
                )
                tool_messages.append(
                    ToolMessage(
                        content=_json_text(
                            {
                                "tool": result.tool,
                                "status": result.status,
                                "summary": result.summary,
                                "payload": result.payload,
                                "error": result.error,
                            }
                        ),
                        tool_call_id=str(call.get("id") or tool_call["id"]),
                        name=tool_name,
                        status="error" if result.status == "failed" else "success",
                    )
                )
                action_id = result.payload.get("action_id") if isinstance(result.payload, dict) else None
                if action_id:
                    action = self.repository.get_action_proposal(str(action_id))
                    if action:
                        pending_actions.append(action)
                if result.tool == "finalize":
                    final_output = parse_agent_output(_json_text(result.payload)).model_dump() if result.payload else {
                        "summary": result.summary or "Agent 已完成",
                        "raw_output": "",
                        "needs_manual_review": False,
                        "requires_approval": bool(step.get("requires_approval")),
                        "next_action": "",
                        "tasks": [],
                        "risks": [],
                        "artifacts": [],
                    }
            except Exception as exc:
                duration_ms = int((perf_counter() - start_perf) * 1000)
                self.repository.update_tool_call(
                    tool_call["id"],
                    status="failed",
                    error=str(exc),
                    completed_at=datetime.now().isoformat(),
                    duration_ms=duration_ms,
                )
                self.repository.add_event(
                    project["id"],
                    task["id"],
                    "tool_call_failed",
                    step["agent_id"],
                    f"工具 {tool_name} 执行失败：{exc}",
                    {"tool_call_id": tool_call["id"], "tool_name": tool_name},
                )
                tool_messages.append(
                    ToolMessage(
                        content=_json_text({"tool": tool_name, "status": "failed", "error": str(exc)}),
                        tool_call_id=str(call.get("id") or tool_call["id"]),
                        name=tool_name,
                        status="error",
                    )
                )
                results.append({"tool": tool_name, "status": "failed", "error": str(exc), "payload": {}, "summary": ""})

        return {
            "messages": tool_messages,
            "pending_tool_calls": [],
            "pending_actions": pending_actions,
            "tool_results": results,
            "final_output": final_output,
        }

    async def action_gate_node(self, state: WorkflowState) -> dict[str, Any]:
        pending_actions = list(state.get("pending_actions") or [])
        if not pending_actions:
            return {"interrupt_kind": None, "interrupt_payload": None}

        step = self._current_step(state)
        task = self._current_task(state)
        project = self._project(state)
        remaining: list[dict[str, Any]] = []
        for action in pending_actions:
            refreshed = self.repository.get_action_proposal(action["id"]) or action
            status = refreshed.get("status")
            if status in {"executed", "completed"}:
                self.repository.add_event(
                    project["id"],
                    task["id"] if task else None,
                    "action_executed",
                    step["agent_id"] if step else "agent",
                    f"动作已执行：{refreshed.get('title')}",
                    {"action_id": refreshed["id"], "action_type": refreshed.get("action_type")},
                )
                continue
            if status == "approved":
                executed = self.action_service.execute(refreshed["id"])
                self.repository.add_event(
                    project["id"],
                    task["id"] if task else None,
                    "approval_granted",
                    "user",
                    "动作已批准，继续执行",
                    {"action_id": executed["id"], "action_type": executed.get("action_type")},
                )
                self.repository.add_event(
                    project["id"],
                    task["id"] if task else None,
                    "action_executed" if executed.get("status") == "executed" else "action_failed",
                    step["agent_id"] if step else "agent",
                    f"动作已执行：{executed.get('title')}" if executed.get("status") == "executed" else f"动作执行失败：{executed.get('title')}",
                    {"action_id": executed["id"], "status": executed.get("status")},
                )
                continue
            if status in {"failed", "rejected", "blocked"}:
                self.repository.add_event(
                    project["id"],
                    task["id"] if task else None,
                    "action_failed",
                    step["agent_id"] if step else "agent",
                    f"动作未完成：{refreshed.get('title')}",
                    {"action_id": refreshed["id"], "status": status},
                )
                continue

            payload = {
                "interrupt_kind": "action_approval",
                "workflow_id": project["id"],
                "step_id": task["id"] if task else None,
                "action_id": refreshed["id"],
                "action_type": refreshed.get("action_type"),
                "title": refreshed.get("title"),
                "description": refreshed.get("description"),
                "policy_reason": (refreshed.get("payload") or {}).get("_policy_reason"),
            }
            self.repository.update_project(project["id"], status="awaiting_approval", current_stage=f"{step['step_key']}_approval")
            self.repository.add_event(
                project["id"],
                task["id"] if task else None,
                "approval_needed",
                step["agent_id"] if step else "agent",
                f"动作等待审批：{refreshed.get('title')}",
                payload,
            )
            decision = interrupt(payload)
            logger.info("LangGraph action interrupt resumed: %s", decision)
            latest = self.repository.get_action_proposal(refreshed["id"]) or refreshed
            if latest.get("status") == "approved":
                executed = self.action_service.execute(latest["id"])
                self.repository.add_event(
                    project["id"],
                    task["id"] if task else None,
                    "approval_granted",
                    "user",
                    "动作已批准，继续执行",
                    {"action_id": executed["id"], "action_type": executed.get("action_type")},
                )
                self.repository.add_event(
                    project["id"],
                    task["id"] if task else None,
                    "action_executed" if executed.get("status") == "executed" else "action_failed",
                    step["agent_id"] if step else "agent",
                    f"动作已执行：{executed.get('title')}" if executed.get("status") == "executed" else f"动作执行失败：{executed.get('title')}",
                    {"action_id": executed["id"], "status": executed.get("status")},
                )
            elif latest.get("status") == "pending_approval":
                remaining.append(latest)
            elif latest.get("status") in {"executed", "completed"}:
                self.repository.add_event(
                    project["id"],
                    task["id"] if task else None,
                    "approval_granted",
                    "user",
                    "动作已批准并恢复工作流",
                    {"action_id": latest["id"]},
                )
            elif latest.get("status") in {"rejected", "failed"}:
                self.repository.add_event(
                    project["id"],
                    task["id"] if task else None,
                    "approval_granted",
                    "user",
                    "动作审批流程已结束",
                    {"action_id": latest["id"], "status": latest.get("status")},
                )

        return {"pending_actions": remaining, "interrupt_kind": None, "interrupt_payload": None}

    async def review_gate_node(self, state: WorkflowState) -> dict[str, Any]:
        step = self._current_step(state)
        task = self._current_task(state)
        project = self._project(state)
        if step is None or task is None:
            return {"execution_state": "completed"}

        output = state.get("final_output") or {
            "summary": "模型未返回结构化结束结果，需要人工检查。",
            "raw_output": "",
            "needs_manual_review": True,
            "requires_approval": True,
            "next_action": "检查当前工作流输出并决定是否重试。",
            "tasks": [],
            "risks": [],
            "artifacts": [],
        }

        needs_approval = bool(step.get("requires_approval"))
        approved = True
        comment: str | None = None
        if needs_approval:
            payload = {
                "interrupt_kind": "step_approval",
                "workflow_id": project["id"],
                "step_id": task["id"],
                "step_key": step["step_key"],
                "title": step["title"],
                "description": step["description"],
            }
            self.repository.update_project(project["id"], status="awaiting_approval", current_stage=f"{step['step_key']}_approval")
            self.repository.update_task(task["id"], status=TaskStatus.AWAITING_APPROVAL.value, output=output)
            self.repository.add_event(project["id"], task["id"], "approval_needed", step["agent_id"], f"{step['title']} 等待审批", payload)
            decision = interrupt(payload) or {}
            approved = bool(decision.get("approved", True))
            comment = decision.get("comment")
            if approved:
                self.repository.add_event(project["id"], task["id"], "approval_granted", "user", comment or "审批通过")
            else:
                self.repository.update_task(task["id"], status=TaskStatus.FAILED.value, output=output, error=comment)
                self.repository.update_project(project["id"], status="failed", current_stage=step["step_key"])
                self.repository.add_event(project["id"], task["id"], "approval_rejected", "user", comment or "审批未通过")
                return {"execution_state": "failed", "approval_comment": comment}

        self.repository.update_task(
            task["id"],
            status=TaskStatus.COMPLETED.value,
            output=output,
            completed_at=datetime.now().isoformat(),
        )
        self.repository.add_artifact(
            project["id"],
            task["id"],
            step.get("artifact_type") or "workflow_output",
            step.get("artifact_title") or step["title"],
            output,
        )

        next_step_index = int(state.get("step_index", 0)) + 1
        workflow_steps = list((state.get("metadata") or {}).get("workflow_steps") or [])
        if next_step_index >= len(workflow_steps):
            self.repository.update_project(
                project["id"],
                status="completed",
                current_stage="completed",
                completed_at=datetime.now().isoformat(),
            )
            self.repository.add_event(project["id"], task["id"], "done", step["agent_id"], "工作流已完成")
            return {
                "execution_state": "completed",
                "approval_comment": comment,
                "current_task_id": task["id"],
            }

        metadata = dict(state.get("metadata") or {})
        metadata["step_started_at"] = None
        return {
            "step_index": next_step_index,
            "current_task_id": None,
            "current_step": workflow_steps[next_step_index]["step_key"],
            "current_agent_id": workflow_steps[next_step_index]["agent_id"],
            "messages": [],
            "pending_tool_calls": [],
            "pending_actions": [],
            "tool_results": [],
            "final_output": None,
            "execution_state": "created",
            "approval_comment": comment,
            "metadata": metadata,
        }

    async def curate_memory_node(self, state: WorkflowState) -> dict[str, Any]:
        workflow_id = state["workflow_id"]
        if self.memory_curator:
            try:
                await self.memory_curator.curate_completed_workflow(workflow_id)
            except Exception as exc:
                logger.info("Workflow memory curation failed: %s", exc)
                self.repository.add_event(workflow_id, None, "memory_warning", "system", f"工作流记忆沉淀失败：{exc}")
        return {"execution_state": "completed"}

    def _tool_schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "list_files",
                    "description": "列出项目中的文件，适合先快速了解目录结构。",
                    "parameters": {
                        "type": "object",
                        "properties": {"pattern": {"type": "string", "description": "glob 模式，默认 **/*"}},
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_code",
                    "description": "按关键词搜索代码片段。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "path_glob": {"type": "string"},
                            "max_results": {"type": "integer"},
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "读取单个文件内容。",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "inspect_project",
                    "description": "检查项目结构和关键配置。",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "detect_project_commands",
                    "description": "识别可用的构建、测试和类型检查命令。",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_git_status",
                    "description": "查看当前 git 状态。",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_git_diff",
                    "description": "查看 git diff。",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_changed_files",
                    "description": "列出已改动文件。",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "propose_patch",
                    "description": "提出补丁建议，不直接写文件。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "description": {"type": "string"},
                            "payload": {"type": "object"},
                        },
                        "required": ["payload"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "propose_command",
                    "description": "提出命令执行建议，不直接运行命令。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "description": {"type": "string"},
                            "payload": {"type": "object"},
                        },
                        "required": ["payload"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "read_execution_result",
                    "description": "读取动作执行结果。",
                    "parameters": {"type": "object", "properties": {"action_id": {"type": "string"}}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "read_test_failures",
                    "description": "查看测试失败明细。",
                    "parameters": {"type": "object", "properties": {"action_id": {"type": "string"}}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "finalize",
                    "description": "在当前 step 完成时收口，返回结构化总结。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "summary": {"type": "string"},
                            "tasks": {"type": "array", "items": {"type": "string"}},
                            "risks": {"type": "array", "items": {"type": "string"}},
                            "next_action": {"type": "string"},
                            "requires_approval": {"type": "boolean"},
                            "artifacts": {"type": "array"},
                        },
                        "required": ["summary"],
                    },
                },
            },
        ]

    def _build_step_messages(self, project: dict[str, Any], state: WorkflowState, step: dict[str, Any], task: dict[str, Any]) -> list[Any]:
        context = self._context_for_step(project, state, step, task)
        agent = ((state.get("metadata") or {}).get("workflow_agents") or {}).get(step["agent_id"], {})
        step_input = {
            "agent": agent,
            "step": step,
            "previous_outputs": self._previous_outputs(project, step),
        }
        raw_messages = self.runner._build_messages(step["agent_id"], context, step_input)
        converted: list[Any] = []
        for item in raw_messages:
            role = item.get("role")
            content = item.get("content", "")
            if role == "system":
                converted.append(SystemMessage(content=content))
            elif role == "assistant":
                converted.append(AIMessage(content=content))
            else:
                converted.append(HumanMessage(content=content))
        return converted

    def _context_for_step(
        self,
        project: dict[str, Any],
        state: WorkflowState,
        step: dict[str, Any],
        task: dict[str, Any],
    ) -> RuntimeExecutionContext:
        workflow_steps = (state.get("metadata") or {}).get("workflow_steps") or []
        previous_outputs = self._previous_outputs(project, step)
        fallback_context = self._project_context(project.get("project_path"), project.get("goal", ""))
        if self.context_builder:
            workflow_stub = type("WorkflowStub", (), {"steps": [], "id": project.get("template_id")})
            step_stub = type("StepStub", (), {**step})
            built = self.context_builder.build_for_step(
                project=project,
                workflow=workflow_stub,
                step=step_stub,
                task={"id": task["id"], "step_key": step["step_key"]},
                previous_outputs=previous_outputs,
                fallback_project_context=fallback_context,
            )
            return built
        return RuntimeExecutionContext(
            workflow_id=project["id"],
            goal=project["goal"],
            project_path=project.get("project_path"),
            project_context=fallback_context,
            provider=project["provider"],
            model=project.get("model"),
            context_pack={"workflow_steps": workflow_steps},
        )

    def _previous_outputs(self, project: dict[str, Any], step: dict[str, Any]) -> list[dict[str, Any]]:
        outputs: list[dict[str, Any]] = []
        for task in project.get("tasks", []) or []:
            if int(task.get("sort_order") or 0) < int(step.get("sort_order") or 0) and task.get("output"):
                outputs.append(task["output"])
        return outputs

    def _ensure_task(self, project: dict[str, Any], state: WorkflowState, step: dict[str, Any]) -> dict[str, Any]:
        current_task = self._current_task(state)
        if current_task:
            return current_task
        existing = next(
            (
                task
                for task in project.get("tasks", []) or []
                if task.get("step_key") == step["step_key"] and task.get("status") != TaskStatus.FAILED.value
            ),
            None,
        )
        if existing:
            return existing
        task = self.repository.create_task(
            project_id=project["id"],
            role=step["agent_id"],
            title=step["title"],
            description=step["description"],
            status=TaskStatus.RUNNING.value,
            input_data={"goal": project.get("goal"), "previous_outputs": self._previous_outputs(project, step)},
            requires_approval=bool(step.get("requires_approval")),
            step_key=step["step_key"],
            sort_order=int(step.get("sort_order") or state.get("step_index", 0)),
        )
        self.repository.add_event(project["id"], task["id"], "workflow_event", step["agent_id"], f"{step['title']} 开始执行")
        return task

    def _current_task(self, state: WorkflowState) -> dict[str, Any] | None:
        task_id = state.get("current_task_id")
        if not task_id:
            return None
        return self.repository.get_task(task_id)

    def _current_step(self, state: WorkflowState) -> dict[str, Any] | None:
        metadata = state.get("metadata") or {}
        workflow_steps = metadata.get("workflow_steps") or []
        step_index = int(state.get("step_index", 0) or 0)
        if 0 <= step_index < len(workflow_steps):
            return workflow_steps[step_index]
        return None

    def _project(self, state: WorkflowState) -> dict[str, Any]:
        project = self.repository.get_project(state["workflow_id"])
        if not project:
            raise RuntimeError(f"Workflow project not found: {state['workflow_id']}")
        return project

    def _project_context(self, project_path: str | None, goal: str) -> str:
        if not project_path:
            return ""
        try:
            from context.service import get_context_service

            service = get_context_service()
            return service.get_context_for_chat(query=goal, project_path=project_path, max_length=1800)
        except Exception as exc:
            logger.info("Workflow project context unavailable: %s", exc)
            return ""


async def execute_tool_bridge_node(state: WorkflowState) -> dict[str, Any]:
    """Compatibility node retained for Phase 1 tests and fallback references."""

    metadata = dict(state.get("metadata") or {})
    bridge_payload = metadata.get("bridge_payload")
    executor = metadata.get("tool_executor")
    project = metadata.get("project") or {}
    if not bridge_payload or executor is None:
        metadata["bridge_status"] = "skipped"
        metadata["bridge_payload"] = None
        return {"metadata": metadata}
    result = execute_legacy_tool(
        executor,
        bridge_payload,
        workflow_id=state["workflow_id"],
        step_id=metadata.get("step_id"),
        agent_id=state.get("current_agent_id") or metadata.get("primary_agent_id") or "planner",
        project=project,
    )
    messages = list(state.get("messages") or [])
    messages.append({"role": "tool", "content": result})
    metadata["bridge_status"] = "completed"
    metadata["bridge_payload"] = None
    return {"messages": messages, "metadata": metadata}
