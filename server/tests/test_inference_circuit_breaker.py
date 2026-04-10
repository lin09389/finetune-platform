import asyncio

import pytest

from api.inference.circuit_breaker import (
    CircuitBreakerOpenError,
    CircuitState,
    InferenceCircuitBreaker,
)


@pytest.mark.asyncio
async def test_circuit_opens_after_failure_threshold():
    breaker = InferenceCircuitBreaker(failure_threshold=2, timeout_seconds=0.5)
    backend = "test-backend"

    await breaker.record_failure(backend, RuntimeError("f1"))
    await breaker.record_failure(backend, RuntimeError("f2"))

    status = breaker.get_status(backend)
    assert status["state"] == CircuitState.OPEN.value
    assert await breaker.can_execute(backend) is False


@pytest.mark.asyncio
async def test_circuit_transitions_to_half_open_after_timeout():
    breaker = InferenceCircuitBreaker(
        failure_threshold=1,
        timeout_seconds=0.05,
        success_threshold=1,
    )
    backend = "test-backend"

    await breaker.record_failure(backend, RuntimeError("boom"))
    await asyncio.sleep(0.06)

    assert await breaker.can_execute(backend) is True
    assert breaker.get_status(backend)["state"] == CircuitState.HALF_OPEN.value


@pytest.mark.asyncio
async def test_execute_with_open_circuit_uses_fallback():
    breaker = InferenceCircuitBreaker(failure_threshold=1, timeout_seconds=999)
    backend = "test-backend"

    async def primary():
        raise RuntimeError("primary failed")

    async def fallback():
        return "fallback-result"

    result = await breaker.execute_with_protection(backend, primary, fallback)
    assert result == "fallback-result"

    result2 = await breaker.execute_with_protection(backend, primary, fallback)
    assert result2 == "fallback-result"


@pytest.mark.asyncio
async def test_execute_with_open_circuit_without_fallback_raises():
    breaker = InferenceCircuitBreaker(failure_threshold=1, timeout_seconds=999)
    backend = "test-backend"

    async def primary():
        raise RuntimeError("primary failed")

    with pytest.raises(RuntimeError):
        await breaker.execute_with_protection(backend, primary)

    with pytest.raises(CircuitBreakerOpenError):
        await breaker.execute_with_protection(backend, primary)
