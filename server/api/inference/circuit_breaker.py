# -*- coding: utf-8 -*-
"""
推理后端熔断器
防止级联故障，支持自动降级
"""
import asyncio
import time
from enum import Enum
from dataclasses import dataclass
from typing import Optional, Callable, Any, Dict
import logging

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitStats:
    failures: int = 0
    successes: int = 0
    last_failure_time: float = 0
    last_success_time: float = 0
    state: CircuitState = CircuitState.CLOSED
    last_error: Optional[str] = None


class InferenceCircuitBreaker:
    """推理后端熔断器"""
    
    def __init__(
        self,
        failure_threshold: int = 3,
        success_threshold: int = 2,
        timeout_seconds: float = 60.0,
        half_open_max_calls: int = 3
    ):
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.timeout_seconds = timeout_seconds
        self.half_open_max_calls = half_open_max_calls
        
        self._circuits: Dict[str, CircuitStats] = {}
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
                    logger.info(f"熔断器 [{backend_name}] 进入半开状态")
                    return True
                logger.debug(f"熔断器 [{backend_name}] 处于开启状态，剩余 {self.timeout_seconds - elapsed:.0f} 秒")
                return False
            
            if circuit.state == CircuitState.HALF_OPEN:
                return circuit.successes < self.half_open_max_calls
        
        return False
    
    async def record_success(self, backend_name: str):
        async with self._lock:
            circuit = self._get_circuit(backend_name)
            circuit.successes += 1
            circuit.failures = 0
            circuit.last_success_time = time.time()
            circuit.last_error = None
            
            if circuit.state == CircuitState.HALF_OPEN:
                if circuit.successes >= self.success_threshold:
                    circuit.state = CircuitState.CLOSED
                    logger.info(f"熔断器 [{backend_name}] 恢复正常")
    
    async def record_failure(self, backend_name: str, error: Exception):
        async with self._lock:
            circuit = self._get_circuit(backend_name)
            circuit.failures += 1
            circuit.last_failure_time = time.time()
            circuit.last_error = str(error)
            
            if circuit.state == CircuitState.HALF_OPEN:
                circuit.state = CircuitState.OPEN
                logger.warning(f"熔断器 [{backend_name}] 重新熔断: {error}")
            elif circuit.failures >= self.failure_threshold:
                circuit.state = CircuitState.OPEN
                logger.warning(
                    f"熔断器 [{backend_name}] 触发熔断 "
                    f"(失败次数: {circuit.failures}/{self.failure_threshold}): {error}"
                )
    
    async def execute_with_protection(
        self,
        backend_name: str,
        func: Callable,
        fallback: Optional[Callable] = None,
        *args,
        **kwargs
    ) -> Any:
        if not await self.can_execute(backend_name):
            if fallback:
                logger.info(f"熔断器 [{backend_name}] 执行降级方案")
                return await fallback(*args, **kwargs)
            raise CircuitBreakerOpenError(
                f"熔断器 [{backend_name}] 处于开启状态，服务暂时不可用"
            )
        
        try:
            result = await func(*args, **kwargs)
            await self.record_success(backend_name)
            return result
        except Exception as e:
            await self.record_failure(backend_name, e)
            if fallback:
                logger.info(f"熔断器 [{backend_name}] 执行失败，使用降级方案: {e}")
                return await fallback(*args, **kwargs)
            raise
    
    def get_status(self, backend_name: str) -> Dict[str, Any]:
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
    
    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        return {
            name: self.get_status(name)
            for name in self._circuits.keys()
        }
    
    async def reset(self, backend_name: str):
        async with self._lock:
            if backend_name in self._circuits:
                self._circuits[backend_name] = CircuitStats()
                logger.info(f"熔断器 [{backend_name}] 已重置")


class CircuitBreakerOpenError(Exception):
    """熔断器开启错误"""
    pass


_circuit_breaker: Optional[InferenceCircuitBreaker] = None


def get_circuit_breaker() -> InferenceCircuitBreaker:
    global _circuit_breaker
    if _circuit_breaker is None:
        _circuit_breaker = InferenceCircuitBreaker()
    return _circuit_breaker
