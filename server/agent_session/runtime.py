from __future__ import annotations

import logging
from typing import Any

from core.config import settings

logger = logging.getLogger(__name__)


class AgentSessionRuntime:
    """Prompt runtime router for LangGraph and processor execution paths."""

    async def run_prompt(
        self,
        service: Any,
        session_id: str,
        content: str,
        session: dict[str, Any],
        *,
        model_call: Any,
        stream_model_call: Any,
    ) -> dict[str, Any]:
        if service._has_custom_processor_prompt():
            logger.info("agent_session prompt routed to custom processor prompt: session_id=%s", session_id)
            return await service.processor.prompt(
                session_id,
                content,
                model_call=model_call,
                stream_model_call=stream_model_call,
            )

        runner = await service._get_graph_runner()
        if runner is not None:
            initial_state = service._build_langgraph_initial_state(session_id, content)
            logger.info(
                "agent_session prompt routed to LangGraph: session_id=%s provider=%s model=%s stream=%s",
                session_id,
                session.get("provider") or "",
                session.get("model") or "",
                bool(stream_model_call),
            )
            try:
                await runner.run_prompt(
                    initial_state,
                    model_call=model_call,
                    stream_model_call=stream_model_call,
                )
                result = service.repository.get_session(session_id) or session
                result["parts"] = service.repository.list_parts(session_id)
                return result
            except Exception as exc:
                logger.exception("agent_session LangGraph prompt failed")
                service._record_langgraph_fallback(session_id, str(exc))
                return service.record_prompt_failure(session_id, exc)

        graph_error = service._graph_runner_error if settings.agent_session_langgraph_enabled else None
        if graph_error:
            service._record_langgraph_fallback(session_id, graph_error)
            return service._record_agent_chain_failure(
                session_id,
                "langgraph_init_failed",
                f"LangGraph 初始化失败，已停止执行，未回退到旧 processor：{graph_error}",
                provider=session.get("provider"),
                model=session.get("model"),
            )

        logger.info(
            "agent_session prompt routed to processor fallback: session_id=%s provider=%s model=%s stream=%s graph_error=%s",
            session_id,
            session.get("provider") or "",
            session.get("model") or "",
            bool(stream_model_call),
            bool(graph_error),
        )
        return await service.processor.prompt(session_id, content, model_call=model_call, stream_model_call=stream_model_call)
