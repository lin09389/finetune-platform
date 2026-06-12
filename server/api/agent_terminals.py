from __future__ import annotations

import json
from typing import Any

import asyncio
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from agent_session.terminal_manager import terminal_manager
from agent_session.service import AgentSessionService
from api.agent_sessions import _user_can_access_session, get_agent_session_service, get_agent_session_user
from core.db_manager import run_sync
from security.jwt_auth import TokenPayload

router = APIRouter(prefix="/agent-terminals", tags=["Agent Terminals"])


@router.websocket("/{terminal_id}/ws")
async def agent_terminal_websocket(
    websocket: WebSocket,
    terminal_id: str,
    service: AgentSessionService = Depends(get_agent_session_service),
    current_user: TokenPayload = Depends(get_agent_session_user),
):
    await websocket.accept()
    session = terminal_manager.get(terminal_id)
    if not session:
        await websocket.send_text(json.dumps({"type": "error", "message": "Terminal not found"}, ensure_ascii=False))
        await websocket.close(code=4404)
        return
    try:
        agent_session = await run_sync(service.get_session, session.session_id)
    except ValueError:
        await websocket.send_text(json.dumps({"type": "error", "message": "Agent session not found"}, ensure_ascii=False))
        await websocket.close(code=4404)
        return
    if not _user_can_access_session(agent_session, current_user):
        await websocket.send_text(json.dumps({"type": "error", "message": "Terminal access denied"}, ensure_ascii=False))
        await websocket.close(code=4403)
        return

    queue = session.subscribe()

    async def send_loop() -> None:
        while True:
            message = await queue.get()
            await websocket.send_text(json.dumps(message, ensure_ascii=False))
            if message.get("type") in {"exit", "error"}:
                break

    async def receive_loop() -> None:
        while True:
            raw = await websocket.receive_text()
            try:
                message: dict[str, Any] = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({"type": "error", "message": "Invalid terminal message"}, ensure_ascii=False))
                continue
            message_type = str(message.get("type") or "")
            if message_type == "input":
                terminal_manager.write(terminal_id, str(message.get("data") or ""))
            elif message_type == "resize":
                try:
                    cols = int(message.get("cols") or 100)
                    rows = int(message.get("rows") or 30)
                    terminal_manager.resize(terminal_id, cols, rows)
                except (ValueError, TypeError):
                    pass
            elif message_type == "interrupt":
                terminal_manager.interrupt(terminal_id)
            elif message_type == "terminate":
                terminal_manager.terminate(terminal_id)
            else:
                await websocket.send_text(json.dumps({"type": "error", "message": "Unsupported terminal message"}, ensure_ascii=False))

    try:
        sender = asyncio.create_task(send_loop())
        receiver = asyncio.create_task(receive_loop())
        done, pending = await asyncio.wait({sender, receiver}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        for task in done:
            try:
                task.result()
            except Exception:
                pass
    except WebSocketDisconnect:
        pass
    finally:
        session.unsubscribe(queue)
