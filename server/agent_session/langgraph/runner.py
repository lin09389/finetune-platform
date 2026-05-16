from __future__ import annotations

from pathlib import Path
from typing import Any

import logging

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

from agent_kernel.langgraph.checkpoint import get_checkpoint_db_path

from .graph_builder import build_agent_session_graph
from .nodes import AgentSessionLangGraphRuntime


logger = logging.getLogger(__name__)


class AgentSessionGraphRunner:
    def __init__(self, repository: Any, processor: Any, model_call: Any = None):
        self.repository = repository
        self.processor = processor
        self.model_call = model_call
        self.runtime = AgentSessionLangGraphRuntime(repository=repository, processor=processor, model_call=model_call)
        self._graph = None
        self._checkpointer: AsyncSqliteSaver | None = None
        self._checkpointer_context = None

    @staticmethod
    def thread_id(session_id: str) -> str:
        return f"agent_session:{session_id}"

    async def _get_checkpointer(self) -> AsyncSqliteSaver:
        if self._checkpointer is None:
            db_path = str(Path(get_checkpoint_db_path()))
            self._checkpointer_context = AsyncSqliteSaver.from_conn_string(db_path)
            self._checkpointer = await self._checkpointer_context.__aenter__()
            if hasattr(self._checkpointer, "setup"):
                await self._checkpointer.setup()
        return self._checkpointer

    async def get_graph(self):
        if self._graph is None:
            logger.info("agent_session.langgraph.runner building graph")
            self._graph = build_agent_session_graph(
                repository=self.repository,
                processor=self.processor,
                model_call=self.model_call,
                checkpointer=await self._get_checkpointer(),
                runtime=self.runtime,
            )
            logger.info("agent_session.langgraph.runner graph built successfully")
        return self._graph

    async def run_prompt(
        self,
        initial_state: dict[str, Any],
        *,
        model_call: Any = None,
        stream_model_call: Any = None,
    ) -> None:
        session_id = str(initial_state.get("session_id") or "")
        graph = await self.get_graph()
        self.runtime.set_invocation_context(
            session_id,
            model_call=model_call,
            stream_model_call=stream_model_call,
        )
        try:
            logger.info(
                "agent_session.langgraph.run_prompt start: session_id=%s model_call=%s stream_model_call=%s",
                session_id,
                bool(model_call),
                bool(stream_model_call),
            )
            await graph.ainvoke(
                initial_state,
                config={"configurable": {"thread_id": self.thread_id(session_id)}},
            )
            logger.info("agent_session.langgraph.run_prompt completed: session_id=%s", session_id)
        finally:
            self.runtime.clear_invocation_context(session_id)

    async def resume(
        self,
        session_id: str,
        decision: dict[str, Any],
        *,
        model_call: Any = None,
        stream_model_call: Any = None,
    ) -> None:
        graph = await self.get_graph()
        self.runtime.set_invocation_context(
            session_id,
            model_call=model_call,
            stream_model_call=stream_model_call,
        )
        try:
            await graph.ainvoke(
                Command(resume=decision),
                config={"configurable": {"thread_id": self.thread_id(session_id)}},
            )
        finally:
            self.runtime.clear_invocation_context(session_id)

    async def execute_action_and_resume(
        self,
        part_id: str,
        decision: dict[str, Any],
        *,
        model_call: Any = None,
        stream_model_call: Any = None,
    ) -> dict[str, Any]:
        part = self.repository.get_part(part_id)
        session_id = str((part or {}).get("session_id") or "")
        if not session_id:
            raise ValueError("Agent part session not found")
        if part and str(part.get("status") or "") == "approved":
            await self.runtime.action_exec_node({"session_id": session_id, "pending_part_id": part_id})
        await self.resume(
            session_id,
            decision,
            model_call=model_call,
            stream_model_call=stream_model_call,
        )
        return self.repository.get_part(part_id) or part or {}

    async def run_prompt_legacy(
        self,
        session_id: str,
        content: str,
        *,
        model_call: Any = None,
        stream_model_call: Any = None,
    ) -> dict[str, Any]:
        graph = await self.get_graph()
        initial_state = {"session_id": session_id, "prompt": content}
        self.runtime.set_invocation_context(
            session_id,
            model_call=model_call,
            stream_model_call=stream_model_call,
        )
        try:
            await graph.ainvoke(
                initial_state,
                config={"configurable": {"thread_id": self.thread_id(session_id)}},
            )
            return self.repository.get_session(session_id) or {}
        finally:
            self.runtime.clear_invocation_context(session_id)
