from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator

from .deepagents_runtime import CallableToolCallingChatModel
from .execution_context import RuntimeExecutionContext
from .model_adapter import ProviderAdapterError, get_chat_model, resolve_official_model_spec
from .permission import permission_policy_for_agent


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
        payload: dict[str, Any] = {"messages": messages}
        if context_files:
            payload["files"] = context_files
        config = {"configurable": {"thread_id": f"project_chat:{uuid.uuid4().hex}"}}
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
        from deepagents import create_deep_agent
        from deepagents.backends import CompositeBackend, FilesystemBackend, StateBackend

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

        backend = CompositeBackend(
            default=StateBackend(),
            routes={
                "/workspace/": FilesystemBackend(root_dir=self.project_path, virtual_mode=True),
            },
        )
        memory = ["/workspace/AGENTS.md"] if (Path(self.project_path) / "AGENTS.md").is_file() else []
        permission_policy = permission_policy_for_agent(None, "project_chat", self.metadata)
        return create_deep_agent(
            model=model,
            tools=[],
            system_prompt=_project_chat_system_prompt(),
            backend=backend,
            memory=memory,
            permissions=permission_policy.filesystem_permissions(),
            checkpointer=False,
        )


def _project_chat_system_prompt() -> str:
    return (
        "你是 Finetune Platform 的只读项目讨论助手。"
        "用户在普通 Chat 中讨论项目时，你可以使用 DeepAgents 官方文件系统工具查看项目。"
        "真实项目根目录挂载在 `/workspace/`，优先使用 ls、glob、grep、read_file 理解代码。"
        "上下文文件可能位于 `/context/`。"
        "你禁止写入文件、编辑文件或执行命令；不要调用 write_file、edit_file、execute。"
        "如果用户需要修改代码、安装依赖、运行测试或执行命令，请明确说明需要升级为 Agent Task。"
        "回答时直接给出基于项目文件的结论，并尽量引用具体文件路径。"
    )


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
