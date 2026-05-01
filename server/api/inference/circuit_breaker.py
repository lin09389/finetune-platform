"""
Inference backend circuit breaker.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitStats:
    failures: int = 0
    successes: int = 0
    last_failure_time: float = 0.0
    last_success_time: float = 0.0
    state: CircuitState = CircuitState.CLOSED
    last_error: str | None = None


class InferenceCircuitBreaker:
    """Circuit breaker for model backend fallbacks."""

    def __init__(
        self,
        failure_threshold: int = 3,
        success_threshold: int = 2,
        timeout_seconds: float = 60.0,
        half_open_max_calls: int = 3,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.timeout_seconds = timeout_seconds
        self.half_open_max_calls = half_open_max_calls
        self._circuits: dict[str, CircuitStats] = {}
        self._lock = asyncio.Lock()

    def _get_circuit(self, backend_name: str) -> CircuitStats:
        if backend_name not in self._circuits:
            self._circuits[backend_name] = CircuitStats()
        return self._circuits[backend_name]

    async def can_execute(self, backend_name: str) -> bool:
        async with self._lock:
            circuit = self._get_circuit(backend_name)

            if circuit.state == CircuitState.CLOSED:
                return True

            if circuit.state == CircuitState.OPEN:
                elapsed = time.time() - circuit.last_failure_time
                if elapsed >= self.timeout_seconds:
                    circuit.state = CircuitState.HALF_OPEN
                    circuit.successes = 0
                    logger.info("Circuit [%s] enters half-open", backend_name)
                    return True

                logger.debug(
                    "Circuit [%s] still open, remaining %.1fs",
                    backend_name,
                    self.timeout_seconds - elapsed,
                )
                return False

            if circuit.state == CircuitState.HALF_OPEN:
                return circuit.successes < self.half_open_max_calls

            return False

    async def record_success(self, backend_name: str) -> None:
        async with self._lock:
            circuit = self._get_circuit(backend_name)
            circuit.successes += 1
            circuit.failures = 0
            circuit.last_success_time = time.time()
            circuit.last_error = None

            if (
                circuit.state == CircuitState.HALF_OPEN
                and circuit.successes >= self.success_threshold
            ):
                circuit.state = CircuitState.CLOSED
                logger.info("Circuit [%s] recovered to closed", backend_name)

    async def record_failure(self, backend_name: str, error: Exception) -> None:
        async with self._lock:
            circuit = self._get_circuit(backend_name)
            circuit.failures += 1
            circuit.last_failure_time = time.time()
            circuit.last_error = str(error)

            if circuit.state == CircuitState.HALF_OPEN:
                circuit.state = CircuitState.OPEN
                logger.warning("Circuit [%s] re-opened: %s", backend_name, error)
                return

            if circuit.failures >= self.failure_threshold:
                circuit.state = CircuitState.OPEN
                logger.warning(
                    "Circuit [%s] opened (%s/%s): %s",
                    backend_name,
                    circuit.failures,
                    self.failure_threshold,
                    error,
                )

    async def execute_with_protection(
        self,
        backend_name: str,
        func: Callable[..., Awaitable[Any]],
        fallback: Callable[..., Awaitable[Any]] | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        if not await self.can_execute(backend_name):
            if fallback is not None:
                logger.info("Circuit [%s] open, running fallback", backend_name)
                return await fallback(*args, **kwargs)
            raise CircuitBreakerOpenError(
                f"Circuit [{backend_name}] is open; service temporarily unavailable"
            )

        try:
            result = await func(*args, **kwargs)
            await self.record_success(backend_name)
            return result
        except Exception as e:
            await self.record_failure(backend_name, e)
            if fallback is not None:
                logger.info(
                    "Primary execution failed on [%s], fallback: %s",
                    backend_name,
                    e,
                )
                return await fallback(*args, **kwargs)
            raise

    async def execute_stream_with_protection(
        self,
        backend_name: str,
        func: Callable[..., Any],
        fallback: Callable[..., Any] | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Protect an async generator/stream function."""
        if not await self.can_execute(backend_name):
            if fallback is not None:
                logger.info("Circuit [%s] open, running stream fallback", backend_name)
                async for chunk in fallback(*args, **kwargs):
                    yield chunk
                return
            raise CircuitBreakerOpenError(
                f"Circuit [{backend_name}] is open; service temporarily unavailable"
            )

        try:
            gen = func(*args, **kwargs)
            # Try to get the first chunk to test the connection
            try:
                # Use a small timeout or just direct wait, depends on stream
                # Here we just rely on standard iteration
                first_chunk = await gen.__anext__()
            except StopAsyncIteration:
                await self.record_success(backend_name)
                return
            except Exception as e:
                await self.record_failure(backend_name, e)
                if fallback is not None:
                    logger.info("Primary stream failed on first chunk on [%s], fallback: %s", backend_name, e)
                    async for chunk in fallback(*args, **kwargs):
                        yield chunk
                    return
                raise

            # Yield the first chunk and record success
            yield first_chunk
            await self.record_success(backend_name)

            # Continue yielding the rest
            async for chunk in gen:
                yield chunk

        except Exception as e:
            # If it fails later in the stream, we just log and raise, since we can't easily fallback halfway
            logger.error("Stream failed mid-flight on [%s]: %s", backend_name, e)
            raise

    def get_status(self, backend_name: str) -> dict[str, Any]:
        circuit = self._get_circuit(backend_name)
        return {
            "backend": backend_name,
            "state": circuit.state.value,
            "failures": circuit.failures,
            "successes": circuit.successes,
            "last_failure_time": circuit.last_failure_time,
            "last_success_time": circuit.last_success_time,
            "last_error": circuit.last_error,
            "failure_threshold": self.failure_threshold,
            "success_threshold": self.success_threshold,
            "timeout_seconds": self.timeout_seconds,
        }

    def get_all_status(self) -> dict[str, dict[str, Any]]:
        return {name: self.get_status(name) for name in self._circuits}

    async def reset(self, backend_name: str) -> None:
        async with self._lock:
            if backend_name in self._circuits:
                self._circuits[backend_name] = CircuitStats()
                logger.info("Circuit [%s] reset", backend_name)


class CircuitBreakerOpenError(Exception):
    """Raised when circuit is open and no fallback is available."""


_circuit_breaker: InferenceCircuitBreaker | None = None


def get_circuit_breaker() -> InferenceCircuitBreaker:
    global _circuit_breaker
    if _circuit_breaker is None:
        _circuit_breaker = InferenceCircuitBreaker()
    return _circuit_breaker
