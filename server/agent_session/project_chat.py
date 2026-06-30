from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .deepagents_runtime import CallableToolCallingChatModel
from .execution_context import RuntimeExecutionContext
from .model_adapter import ProviderAdapterError, get_chat_model, resolve_official_model_spec
from .runtime import prepare_deepagents_files
from .runtime_contract import PROJECT_CHAT_PROMPT, AgentRuntimeContract
from .runtime_factory import DeepAgentsRuntimeFactory


@dataclass(frozen=True)
class ProjectChatResult:
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


def can_use_deepagents_project_chat(provider: str | None, model: str | None) -> bool:
    context = RuntimeExecutionContext(
        session_id="project_chat_probe",
        goal="",
        project_path=None,
        provider=str(provider or ""),
        model=model,
        metadata={},
    )
    return resolve_official_model_spec(context) is not None


class DeepAgentsProjectChatRunner:
    """Read-only DeepAgents harness for ordinary project discussion."""

    def __init__(
        self,
        *,
        provider: str | None,
        model: str | None,
        project_path: str,
        metadata: dict[str, Any] | None = None,
        model_call: Any = None,
    ):
        self.provider = provider
        self.model = model
        self.project_path = str(Path(project_path).resolve())
        self.metadata = dict(metadata or {})
        self.model_call = model_call

    async def run(
        self,
        messages: list[dict[str, Any]],
        *,
        context_files: dict[str, str] | None = None,
    ) -> ProjectChatResult:
        content = ""
        metadata: dict[str, Any] = {}
        async for event in self.astream_events(messages, context_files=context_files):
            if event.get("type") == "text_delta":
                content += str(event.get("content") or "")
            elif event.get("type") == "metadata":
                metadata.update(event)
        return ProjectChatResult(content=_friendly_readonly_content(content.strip()), metadata=metadata)

    async def astream_events(
        self,
        messages: list[dict[str, Any]],
        *,
        context_files: dict[str, str] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        graph = self._build_graph()
        config = {"configurable": {"thread_id": f"project_chat:{uuid.uuid4().hex}"}}
        payload: dict[str, Any] = {"messages": messages}
        if context_files:
            payload["files"] = await prepare_deepagents_files(graph, config, context_files)
        final_text = ""
        tool_names: list[str] = []
        async for event in graph.astream_events(payload, config=config, version="v2"):
            kind = str(event.get("event") or "")
            if kind == "on_tool_start":
                name = str(event.get("name") or "tool")
                tool_names.append(name)
                yield {"type": "metadata", "project_chat_tools": list(tool_names)}
            elif kind == "on_chat_model_stream":
                delta = _event_text_delta(event)
                if delta:
                    final_text += delta
                    yield {"type": "text_delta", "content": delta}
            elif kind in {"on_chat_model_end", "on_chain_end"}:
                summary = _extract_summary(event)
                if summary and not final_text:
                    final_text = _friendly_readonly_content(summary)
                    yield {"type": "text_delta", "content": final_text}
        yield {
            "type": "metadata",
            "project_chat": True,
            "project_chat_readonly": True,
            "project_chat_root": self.project_path,
            "project_chat_tools": tool_names,
        }

    def _build_graph(self) -> Any:
        if self.model_call is not None:
            model = CallableToolCallingChatModel(self.model_call).model
        else:
            context = RuntimeExecutionContext(
                session_id=f"project_chat_{uuid.uuid4().hex}",
                goal="project chat",
                project_path=self.project_path,
                provider=str(self.provider or ""),
                model=self.model,
                metadata=self.metadata,
            )
            try:
                model = get_chat_model(context)
            except ProviderAdapterError:
                raise

        contract = AgentRuntimeContract.for_project_chat(
            project_path=self.project_path,
            model=model,
            metadata=self.metadata,
            session_id=f"project_chat:{uuid.uuid4().hex}",
        )
        return DeepAgentsRuntimeFactory().build(contract)


def _project_chat_system_prompt() -> str:
    return PROJECT_CHAT_PROMPT


def _event_text_delta(event: dict[str, Any]) -> str:
    chunk = (event.get("data") or {}).get("chunk")
    delta = getattr(chunk, "content", None)
    if isinstance(delta, list):
        return "".join(str(item.get("text", "")) if isinstance(item, dict) else str(item) for item in delta)
    return delta if isinstance(delta, str) else ""


def _extract_summary(event: dict[str, Any]) -> str:
    data = event.get("data") or {}
    output = data.get("output")
    if isinstance(output, dict):
        messages = output.get("messages")
        if isinstance(messages, list) and messages:
            content = getattr(messages[-1], "content", "")
            return content if isinstance(content, str) else str(content)
    content = getattr(output, "content", "")
    return content if isinstance(content, str) else ""


def _friendly_readonly_content(content: str) -> str:
    if "permission denied for write" not in content.lower():
        return content
    return (
        "普通聊天现在是只读项目模式，不能修改文件。"
        "如果你需要我改代码、写文件或运行命令，请升级为 Agent Task。"
    )


__all__ = [
    "DeepAgentsProjectChatRunner",
    "ProjectChatResult",
    "can_use_deepagents_project_chat",
]
