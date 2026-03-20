"""
流式输出工具模块
优化�?SSE 流式响应实现，支持批量推送、背压控制和延迟监控
"""
from typing import AsyncGenerator, Callable, Any, Dict, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
import asyncio
import json
import logging
import time
from collections import deque
from contextlib import asynccontextmanager

from core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class TokenLatencyRecord:
    """单个 token 延迟记录"""
    token: str
    generated_at: float
    pushed_at: float
    latency_ms: float


@dataclass
class StreamingLatencyStats:
    """流式延迟统计"""
    records: List[TokenLatencyRecord] = field(default_factory=list)
    total_tokens: int = 0
    start_time: float = 0.0
    end_time: float = 0.0

    def add_record(self, token: str, generated_at: float, pushed_at: float):
        """添加延迟记录"""
        latency_ms = (pushed_at - generated_at) * 1000
        record = TokenLatencyRecord(
            token=token,
            generated_at=generated_at,
            pushed_at=pushed_at,
            latency_ms=latency_ms
        )
        self.records.append(record)
        self.total_tokens += 1

    def start(self):
        """开始计�?""
        self.start_time = time.time()

    def finish(self):
        """结束计时"""
        self.end_time = time.time()

    @property
    def elapsed_seconds(self) -> float:
        """经过时间（秒�?""
        if self.end_time == 0:
            return time.time() - self.start_time
        return self.end_time - self.start_time

    @property
    def avg_latency_ms(self) -> float:
        """平均延迟（毫秒）"""
        if not self.records:
            return 0.0
        return sum(r.latency_ms for r in self.records) / len(self.records)

    @property
    def max_latency_ms(self) -> float:
        """最大延迟（毫秒�?""
        if not self.records:
            return 0.0
        return max(r.latency_ms for r in self.records)

    @property
    def min_latency_ms(self) -> float:
        """最小延迟（毫秒�?""
        if not self.records:
            return 0.0
        return min(r.latency_ms for r in self.records)

    @property
    def p95_latency_ms(self) -> float:
        """P95 延迟（毫秒）"""
        if not self.records:
            return 0.0
        sorted_latencies = sorted(r.latency_ms for r in self.records)
        p95_index = int(len(sorted_latencies) * 0.95)
        return sorted_latencies[min(p95_index, len(sorted_latencies) - 1)]

    @property
    def tokens_per_second(self) -> float:
        """每秒 token �?""
        elapsed = self.elapsed_seconds
        if elapsed == 0:
            return 0.0
        return self.total_tokens / elapsed

    def to_dict(self) -> Dict[str, Any]:
        """转换为字�?""
        return {
            "total_tokens": self.total_tokens,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "tokens_per_second": round(self.tokens_per_second, 2),
            "latency": {
                "avg_ms": round(self.avg_latency_ms, 2),
                "min_ms": round(self.min_latency_ms, 2),
                "max_ms": round(self.max_latency_ms, 2),
                "p95_ms": round(self.p95_latency_ms, 2),
            },
            "chunk_count": len(self.records),
        }


class BackpressureController:
    """背压控制�?""

    def __init__(
        self,
        max_buffer_size: int = 1000,
        check_interval_ms: int = 10,
        pause_threshold: float = 0.8,
        resume_threshold: float = 0.5
    ):
        self.max_buffer_size = max_buffer_size
        self.check_interval_ms = check_interval_ms
        self.pause_threshold = pause_threshold
        self.resume_threshold = resume_threshold
        self._buffer_size = 0
        self._is_paused = False
        self._pause_event = asyncio.Event()
        self._pause_event.set()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: int = 1) -> bool:
        """获取发送许可，返回是否需要等�?""
        async with self._lock:
            self._buffer_size += tokens
            if self._buffer_size >= self.max_buffer_size * self.pause_threshold:
                if not self._is_paused:
                    self._is_paused = True
                    self._pause_event.clear()
                    logger.debug(f"背压控制：暂停生成，缓冲区大�?{self._buffer_size}")
            return self._is_paused

    async def release(self, tokens: int = 1):
        """释放缓冲区空�?""
        async with self._lock:
            self._buffer_size = max(0, self._buffer_size - tokens)
            if self._is_paused and self._buffer_size <= self.max_buffer_size * self.resume_threshold:
                self._is_paused = False
                self._pause_event.set()
                logger.debug(f"背压控制：恢复生成，缓冲区大�?{self._buffer_size}")

    async def wait_if_paused(self):
        """如果暂停则等�?""
        await self._pause_event.wait()

    @property
    def is_paused(self) -> bool:
        """是否处于暂停状�?""
        return self._is_paused

    @property
    def buffer_usage(self) -> float:
        """缓冲区使用率"""
        return self._buffer_size / self.max_buffer_size

    def get_status(self) -> Dict[str, Any]:
        """获取状�?""
        return {
            "is_paused": self._is_paused,
            "buffer_size": self._buffer_size,
            "max_buffer_size": self.max_buffer_size,
            "buffer_usage": round(self.buffer_usage, 2),
        }


class OptimizedStreamingResponse:
    """
    优化的流式响应类
    支持批量 token 推送、背压控制和延迟监控
    """

    def __init__(
        self,
        generator: AsyncGenerator[str, None],
        buffer_size: Optional[int] = None,
        flush_interval_ms: Optional[int] = None,
        enable_backpressure: Optional[bool] = None,
        on_complete: Optional[Callable[[], Any]] = None,
        on_error: Optional[Callable[[Exception], Any]] = None,
    ):
        settings = get_settings()
        self.buffer_size = buffer_size or settings.stream_buffer_size
        self.flush_interval_ms = flush_interval_ms or settings.stream_flush_interval_ms
        self.enable_backpressure = enable_backpressure if enable_backpressure is not None else settings.enable_backpressure

        self.generator = generator
        self.on_complete = on_complete
        self.on_error = on_error

        self._token_buffer: deque = deque()
        self._latency_stats = StreamingLatencyStats()
        self._backpressure = BackpressureController() if self.enable_backpressure else None
        self._is_flushing = False
        self._last_flush_time = time.time()
        self._lock = asyncio.Lock()

    @property
    def latency_stats(self) -> StreamingLatencyStats:
        """获取延迟统计"""
        return self._latency_stats

    @property
    def backpressure_status(self) -> Optional[Dict[str, Any]]:
        """获取背压状�?""
        if self._backpressure:
            return self._backpressure.get_status()
        return None

    async def _should_flush(self) -> bool:
        """判断是否应该刷新缓冲�?""
        if len(self._token_buffer) >= self.buffer_size:
            return True
        elapsed_ms = (time.time() - self._last_flush_time) * 1000
        if elapsed_ms >= self.flush_interval_ms and len(self._token_buffer) > 0:
            return True
        return False

    async def _flush_buffer(self) -> str:
        """刷新缓冲区，返回 SSE 事件"""
        async with self._lock:
            if not self._token_buffer:
                return ""

            tokens = []
            while self._token_buffer:
                token_data = self._token_buffer.popleft()
                tokens.append(token_data["token"])

            self._last_flush_time = time.time()

            if self._backpressure:
                await self._backpressure.release(len(tokens))

            return await create_sse_event({
                "content": "".join(tokens),
                "done": False,
                "buffered": len(tokens)
            })

    async def _add_token(self, token: str, generated_at: float):
        """添加 token 到缓冲区"""
        pushed_at = time.time()
        self._latency_stats.add_record(token, generated_at, pushed_at)

        async with self._lock:
            self._token_buffer.append({
                "token": token,
                "generated_at": generated_at,
                "pushed_at": pushed_at
            })

        if self._backpressure:
            is_paused = await self._backpressure.acquire()
            if is_paused:
                await self._backpressure.wait_if_paused()

    async def stream(self) -> AsyncGenerator[str, None]:
        """
        流式生成器，支持批量推�?        """
        self._latency_stats.start()
        flush_task = None

        try:
            async for token in self.generator:
                generated_at = time.time()
                await self._add_token(token, generated_at)

                if await self._should_flush():
                    yield await self._flush_buffer()

            if self._token_buffer:
                yield await self._flush_buffer()

            self._latency_stats.finish()

            if self.on_complete:
                if asyncio.iscoroutinefunction(self.on_complete):
                    await self.on_complete()
                else:
                    self.on_complete()

            yield await create_sse_event({
                "done": True,
                "stats": self._latency_stats.to_dict()
            }, "done")

        except Exception as e:
            logger.error(f"流式生成错误：{e}", exc_info=True)
            self._latency_stats.finish()

            if self.on_error:
                if asyncio.iscoroutinefunction(self.on_error):
                    await self.on_error(e)
                else:
                    self.on_error(e)

            yield await create_sse_event({
                "error": str(e),
                "done": True,
                "stats": self._latency_stats.to_dict()
            }, "error")

    async def __aiter__(self):
        async for chunk in self.stream():
            yield chunk


class StreamingResponse:
    """流式响应生成器（兼容旧接口）"""

    def __init__(self, generator: AsyncGenerator[str, None]):
        self.generator = generator

    async def __aiter__(self):
        async for chunk in self.generator:
            yield chunk


async def create_sse_event(data: Dict[str, Any], event_type: str = "message") -> str:
    """
    创建 SSE 事件

    Args:
        data: 数据字典
        event_type: 事件类型

    Returns:
        SSE 格式字符�?    """
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def stream_generator(
    llm_generator: AsyncGenerator[str, None],
    on_chunk: Callable[[str], Any] = None,
    on_complete: Callable[[], Any] = None,
    on_error: Callable[[Exception], Any] = None
) -> AsyncGenerator[str, None]:
    """
    流式生成器包�?
    Args:
        llm_generator: LLM 流式生成�?        on_chunk: 每个 chunk 的回�?        on_complete: 完成回调
        on_error: 错误回调

    Yields:
        SSE 格式数据
    """
    try:
        async for chunk in llm_generator:
            if on_chunk:
                await on_chunk(chunk) if asyncio.iscoroutinefunction(on_chunk) else on_chunk(chunk)

            sse_data = {
                "content": chunk,
                "done": False
            }
            yield await create_sse_event(sse_data)

        if on_complete:
            await on_complete() if asyncio.iscoroutinefunction(on_complete) else on_complete()

        yield await create_sse_event({"done": True}, "done")

    except Exception as e:
        logger.error(f"流式生成错误：{e}", exc_info=True)

        if on_error:
            await on_error(e) if asyncio.iscoroutinefunction(on_error) else on_error(e)

        yield await create_sse_event({
            "error": str(e),
            "done": True
        }, "error")


async def optimized_stream_generator(
    llm_generator: AsyncGenerator[str, None],
    buffer_size: Optional[int] = None,
    flush_interval_ms: Optional[int] = None,
    enable_backpressure: Optional[bool] = None,
    on_chunk: Callable[[str], Any] = None,
    on_complete: Callable[[], Any] = None,
    on_error: Callable[[Exception], Any] = None
) -> AsyncGenerator[str, None]:
    """
    优化的流式生成器，支持批量推送和延迟监控

    Args:
        llm_generator: LLM 流式生成�?        buffer_size: 缓冲区大小（token 数）
        flush_interval_ms: 刷新间隔（毫秒）
        enable_backpressure: 是否启用背压控制
        on_chunk: 每个 chunk 的回�?        on_complete: 完成回调
        on_error: 错误回调

    Yields:
        SSE 格式数据
    """
    streaming = OptimizedStreamingResponse(
        generator=llm_generator,
        buffer_size=buffer_size,
        flush_interval_ms=flush_interval_ms,
        enable_backpressure=enable_backpressure,
        on_complete=on_complete,
        on_error=on_error
    )

    async for chunk in streaming.stream():
        if on_chunk and "content" in chunk:
            try:
                data = json.loads(chunk.split("data: ")[1].split("\n")[0])
                if "content" in data:
                    await on_chunk(data["content"]) if asyncio.iscoroutinefunction(on_chunk) else on_chunk(data["content"])
            except Exception:
                pass
        yield chunk


class TypewriterEffect:
    """打字机效�?""

    def __init__(self, text: str, speed: float = 0.03):
        self.text = text
        self.speed = speed

    async def generate(self) -> AsyncGenerator[str, None]:
        """逐字生成"""
        for char in self.text:
            yield char
            await asyncio.sleep(self.speed)


class StreamStats:
    """流式统计信息"""

    def __init__(self):
        self.total_tokens = 0
        self.start_time = 0
        self.end_time = 0
        self.chunks = []

    def add_chunk(self, chunk: str):
        """添加 chunk 统计"""
        self.chunks.append(chunk)
        self.total_tokens += len(chunk) // 4

    def start(self):
        """开始计�?""
        self.start_time = time.time()

    def finish(self):
        """结束计时"""
        self.end_time = time.time()

    @property
    def elapsed(self) -> float:
        """经过时间"""
        return self.end_time - self.start_time

    @property
    def tokens_per_second(self) -> float:
        """每秒 token �?""
        if self.elapsed == 0:
            return 0
        return self.total_tokens / self.elapsed

    def to_dict(self) -> Dict[str, Any]:
        """转换为字�?""
        return {
            "total_tokens": self.total_tokens,
            "chunk_count": len(self.chunks),
            "elapsed_seconds": round(self.elapsed, 2),
            "tokens_per_second": round(self.tokens_per_second, 2)
        }


@asynccontextmanager
async def streaming_context(
    buffer_size: Optional[int] = None,
    flush_interval_ms: Optional[int] = None,
    enable_backpressure: Optional[bool] = None
):
    """
    流式上下文管理器

    用法�?        async with streaming_context() as ctx:
            async for chunk in ctx.wrap(generator):
                yield chunk
    """
    settings = get_settings()
    ctx = StreamingContext(
        buffer_size=buffer_size or settings.stream_buffer_size,
        flush_interval_ms=flush_interval_ms or settings.stream_flush_interval_ms,
        enable_backpressure=enable_backpressure if enable_backpressure is not None else settings.enable_backpressure
    )
    try:
        yield ctx
    finally:
        await ctx.cleanup()


class StreamingContext:
    """流式上下�?""

    def __init__(
        self,
        buffer_size: int = 10,
        flush_interval_ms: int = 16,
        enable_backpressure: bool = True
    ):
        self.buffer_size = buffer_size
        self.flush_interval_ms = flush_interval_ms
        self.enable_backpressure = enable_backpressure
        self._active_streams: List[OptimizedStreamingResponse] = []

    async def wrap(
        self,
        generator: AsyncGenerator[str, None],
        on_complete: Optional[Callable[[], Any]] = None,
        on_error: Optional[Callable[[Exception], Any]] = None
    ) -> OptimizedStreamingResponse:
        """包装生成器为优化的流式响�?""
        streaming = OptimizedStreamingResponse(
            generator=generator,
            buffer_size=self.buffer_size,
            flush_interval_ms=self.flush_interval_ms,
            enable_backpressure=self.enable_backpressure,
            on_complete=on_complete,
            on_error=on_error
        )
        self._active_streams.append(streaming)
        return streaming

    async def cleanup(self):
        """清理资源"""
        self._active_streams.clear()

    def get_stats(self) -> Dict[str, Any]:
        """获取所有活跃流的统计信�?""
        return {
            "active_streams": len(self._active_streams),
            "streams": [
                {
                    "latency": stream.latency_stats.to_dict(),
                    "backpressure": stream.backpressure_status
                }
                for stream in self._active_streams
            ]
        }


def get_streaming_stats(streaming: OptimizedStreamingResponse) -> Dict[str, Any]:
    """
    获取流式传输统计信息

    Args:
        streaming: 优化的流式响应实�?
    Returns:
        统计信息字典
    """
    return {
        "latency": streaming.latency_stats.to_dict(),
        "backpressure": streaming.backpressure_status,
        "config": {
            "buffer_size": streaming.buffer_size,
            "flush_interval_ms": streaming.flush_interval_ms,
            "enable_backpressure": streaming.enable_backpressure,
        }
    }
