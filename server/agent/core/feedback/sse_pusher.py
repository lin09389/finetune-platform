import asyncio
import json
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set
from pydantic import BaseModel, Field
from fastapi.responses import StreamingResponse

from ..types import ProgressInfo


class SSEEvent(BaseModel):
    event: str = "message"
    data: Dict[str, Any]
    id: Optional[str] = None
    retry: Optional[int] = None


class SSEConnection:
    def __init__(self, connection_id: str, queue: asyncio.Queue):
        self.connection_id = connection_id
        self.queue = queue
        self.created_at = datetime.now()
        self.last_activity = datetime.now()
        self.is_active = True

    async def send(self, event: SSEEvent) -> bool:
        if not self.is_active:
            return False
        
        try:
            self.queue.put_nowait(event)
            self.last_activity = datetime.now()
            return True
        except asyncio.QueueFull:
            return False

    def close(self):
        self.is_active = False


class SSEPusher:
    def __init__(self, heartbeat_interval: int = 30):
        self._connections: Dict[str, SSEConnection] = {}
        self._task_subscribers: Dict[str, Set[str]] = {}
        self._lock = asyncio.Lock()
        self._heartbeat_interval = heartbeat_interval
        self._max_connections = 100
        self._max_queue_size = 100

    async def create_connection(
        self,
        connection_id: str,
        task_ids: Optional[List[str]] = None
    ) -> asyncio.Queue:
        async with self._lock:
            if len(self._connections) >= self._max_connections:
                await self._cleanup_stale_connections()
                
                if len(self._connections) >= self._max_connections:
                    raise RuntimeError("Maximum connections reached")
            
            queue = asyncio.Queue(maxsize=self._max_queue_size)
            connection = SSEConnection(connection_id, queue)
            self._connections[connection_id] = connection
            
            if task_ids:
                for task_id in task_ids:
                    if task_id not in self._task_subscribers:
                        self._task_subscribers[task_id] = set()
                    self._task_subscribers[task_id].add(connection_id)
            
            return queue

    async def close_connection(self, connection_id: str):
        async with self._lock:
            if connection_id in self._connections:
                self._connections[connection_id].close()
                del self._connections[connection_id]
            
            for task_id in list(self._task_subscribers.keys()):
                self._task_subscribers[task_id].discard(connection_id)
                if not self._task_subscribers[task_id]:
                    del self._task_subscribers[task_id]

    async def subscribe_to_task(self, connection_id: str, task_id: str):
        async with self._lock:
            if task_id not in self._task_subscribers:
                self._task_subscribers[task_id] = set()
            self._task_subscribers[task_id].add(connection_id)

    async def unsubscribe_from_task(self, connection_id: str, task_id: str):
        async with self._lock:
            if task_id in self._task_subscribers:
                self._task_subscribers[task_id].discard(connection_id)
                if not self._task_subscribers[task_id]:
                    del self._task_subscribers[task_id]

    async def push_progress(self, task_id: str, progress: ProgressInfo):
        event = SSEEvent(
            event="progress",
            data={
                "task_id": task_id,
                "progress": progress.progress,
                "status": progress.status,
                "message": progress.message,
                "current_step": progress.current_step,
                "total_steps": progress.total_steps,
                "eta_seconds": progress.eta_seconds,
                "timestamp": datetime.now().isoformat()
            }
        )
        await self._broadcast_to_task(task_id, event)

    async def push_status_change(
        self,
        task_id: str,
        old_status: str,
        new_status: str,
        message: str = ""
    ):
        event = SSEEvent(
            event="status_change",
            data={
                "task_id": task_id,
                "old_status": old_status,
                "new_status": new_status,
                "message": message,
                "timestamp": datetime.now().isoformat()
            }
        )
        await self._broadcast_to_task(task_id, event)

    async def push_error(
        self,
        task_id: str,
        error_code: str,
        error_message: str,
        recoverable: bool = True
    ):
        event = SSEEvent(
            event="error",
            data={
                "task_id": task_id,
                "error_code": error_code,
                "error_message": error_message,
                "recoverable": recoverable,
                "timestamp": datetime.now().isoformat()
            }
        )
        await self._broadcast_to_task(task_id, event)

    async def push_custom_event(
        self,
        task_id: str,
        event_type: str,
        data: Dict[str, Any]
    ):
        event = SSEEvent(
            event=event_type,
            data={
                "task_id": task_id,
                **data,
                "timestamp": datetime.now().isoformat()
            }
        )
        await self._broadcast_to_task(task_id, event)

    async def push_heartbeat(self, connection_id: str):
        async with self._lock:
            if connection_id in self._connections:
                connection = self._connections[connection_id]
                event = SSEEvent(
                    event="heartbeat",
                    data={"timestamp": datetime.now().isoformat()}
                )
                await connection.send(event)

    async def _broadcast_to_task(self, task_id: str, event: SSEEvent):
        async with self._lock:
            connection_ids = self._task_subscribers.get(task_id, set()).copy()
        
        disconnected = []
        for conn_id in connection_ids:
            async with self._lock:
                connection = self._connections.get(conn_id)
            
            if connection and connection.is_active:
                success = await connection.send(event)
                if not success:
                    disconnected.append(conn_id)
            else:
                disconnected.append(conn_id)
        
        for conn_id in disconnected:
            await self.close_connection(conn_id)

    async def _cleanup_stale_connections(self):
        now = datetime.now()
        stale_connections = []
        
        async with self._lock:
            for conn_id, connection in self._connections.items():
                inactive_seconds = (now - connection.last_activity).total_seconds()
                if inactive_seconds > 300:
                    stale_connections.append(conn_id)
        
        for conn_id in stale_connections:
            await self.close_connection(conn_id)

    def create_stream_response(
        self,
        connection_id: str,
        queue: asyncio.Queue,
        on_disconnect: Optional[Callable] = None
    ) -> StreamingResponse:
        async def event_generator():
            try:
                while True:
                    try:
                        event = await asyncio.wait_for(
                            queue.get(),
                            timeout=self._heartbeat_interval
                        )
                        yield self._format_sse_event(event)
                    except asyncio.TimeoutError:
                        yield self._format_sse_event(SSEEvent(
                            event="heartbeat",
                            data={"timestamp": datetime.now().isoformat()}
                        ))
            except asyncio.CancelledError:
                pass
            finally:
                if on_disconnect:
                    await self.close_connection(connection_id)
                    if asyncio.iscoroutinefunction(on_disconnect):
                        await on_disconnect()
                    else:
                        on_disconnect()
                else:
                    await self.close_connection(connection_id)
        
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )

    def _format_sse_event(self, event: SSEEvent) -> str:
        lines = []
        
        if event.id:
            lines.append(f"id: {event.id}")
        
        if event.retry:
            lines.append(f"retry: {event.retry}")
        
        lines.append(f"event: {event.event}")
        
        data_str = json.dumps(event.data, ensure_ascii=False)
        for line in data_str.split("\n"):
            lines.append(f"data: {line}")
        
        lines.append("")
        lines.append("")
        
        return "\n".join(lines)

    async def get_connection_count(self) -> int:
        async with self._lock:
            return len(self._connections)

    async def get_task_subscriber_count(self, task_id: str) -> int:
        async with self._lock:
            return len(self._task_subscribers.get(task_id, set()))

    async def broadcast_to_all(self, event: SSEEvent):
        async with self._lock:
            connection_ids = list(self._connections.keys())
        
        for conn_id in connection_ids:
            async with self._lock:
                connection = self._connections.get(conn_id)
            
            if connection and connection.is_active:
                await connection.send(event)
