from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from agent_session.terminal_manager import terminal_manager
from api.agent_sessions import get_agent_session_user
from security.jwt_auth import TokenPayload

router = APIRouter(prefix="/agent-terminals", tags=["Agent Terminals"])


@router.websocket("/{terminal_id}/ws")
async def agent_terminal_websocket(
    websocket: WebSocket,
    terminal_id: str,
    current_user: TokenPayload = Depends(get_agent_session_user),
):
    _ = current_user
    await websocket.accept()
    session = terminal_manager.get(terminal_id)
    if not session:
        await websocket.send_text(json.dumps({"type": "error", "message": "Terminal not found"}, ensure_ascii=False))
        await websocket.close(code=4404)
        return

    queue = session.subscribe()

    async def send_loop() -> None:
        while True:
            message = await queue.get()
            await websocket.send_text(json.dumps(message, ensure_ascii=False))

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
                terminal_manager.resize(terminal_id, int(message.get("cols") or 100), int(message.get("rows") or 30))
            elif message_type == "interrupt":
                terminal_manager.interrupt(terminal_id)
            elif message_type == "terminate":
                terminal_manager.terminate(terminal_id)
            else:
                await websocket.send_text(json.dumps({"type": "error", "message": "Unsupported terminal message"}, ensure_ascii=False))

    try:
        import asyncio

        sender = asyncio.create_task(send_loop())
        receiver = asyncio.create_task(receive_loop())
        done, pending = await asyncio.wait({sender, receiver}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        for task in done:
            task.result()
    except WebSocketDisconnect:
        pass
    finally:
        session.unsubscribe(queue)
