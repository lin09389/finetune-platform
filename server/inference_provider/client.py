from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class InferenceServiceError(RuntimeError):
    code = "inference_service_error"


class InferenceServiceUnavailable(InferenceServiceError):
    code = "inference_service_unavailable"


class InferenceServiceTimeout(InferenceServiceError):
    code = "inference_timeout"


@dataclass(slots=True)
class RemoteResponse:
    status_code: int
    headers: dict[str, str]
    content: bytes


class InferenceServiceClient:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.base_url = self.settings.inference_service_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            trust_env=False,
            timeout=httpx.Timeout(
                connect=self.settings.inference_service_connect_timeout_seconds,
                read=self.settings.inference_service_read_timeout_seconds,
                write=30.0,
                pool=5.0,
            ),
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
            transport=transport,
        )

    @property
    def internal_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.inference_internal_api_key}",
            "X-Internal-Service": "finetune-control-plane",
        }

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Any = None,
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> RemoteResponse:
        request_headers = {**(headers or {}), **self.internal_headers}
        retries = self.settings.inference_service_max_retries
        for attempt in range(retries + 1):
            try:
                response = await self._client.request(
                    method,
                    path,
                    params=params,
                    content=content,
                    headers=request_headers,
                )
                if response.status_code in {502, 503, 504} and attempt < retries:
                    await asyncio.sleep(self.settings.inference_service_retry_delay_seconds * (2**attempt))
                    continue
                return RemoteResponse(
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    content=response.content,
                )
            except httpx.TimeoutException as exc:
                if attempt >= retries:
                    raise InferenceServiceTimeout(str(exc) or "Local inference request timed out") from exc
            except httpx.TransportError as exc:
                if attempt >= retries:
                    raise InferenceServiceUnavailable(str(exc) or "Local inference service unavailable") from exc
            await asyncio.sleep(self.settings.inference_service_retry_delay_seconds * (2**attempt))
        raise InferenceServiceUnavailable("Local inference service unavailable")  # pragma: no cover

    async def open_stream(
        self,
        method: str,
        path: str,
        *,
        params: Any = None,
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        request_headers = {**(headers or {}), **self.internal_headers}
        retries = self.settings.inference_service_max_retries
        for attempt in range(retries + 1):
            request = self._client.build_request(
                method,
                path,
                params=params,
                content=content,
                headers=request_headers,
            )
            try:
                response = await self._client.send(request, stream=True)
                if response.status_code in {502, 503, 504} and attempt < retries:
                    await response.aclose()
                    await asyncio.sleep(self.settings.inference_service_retry_delay_seconds * (2**attempt))
                    continue
                return response
            except httpx.TimeoutException as exc:
                if attempt >= retries:
                    raise InferenceServiceTimeout(str(exc) or "Local inference stream timed out") from exc
            except httpx.TransportError as exc:
                if attempt >= retries:
                    raise InferenceServiceUnavailable(str(exc) or "Local inference service unavailable") from exc
            await asyncio.sleep(self.settings.inference_service_retry_delay_seconds * (2**attempt))
        raise InferenceServiceUnavailable("Local inference service unavailable")  # pragma: no cover

    async def get_json(self, path: str, *, params: Any = None) -> Any:
        response = await self.request("GET", path, params=params)
        if response.status_code >= 400:
            raise InferenceServiceError(
                f"Inference service returned HTTP {response.status_code}: {response.content.decode(errors='replace')}"
            )
        try:
            return httpx.Response(200, content=response.content).json()
        except ValueError as exc:
            raise InferenceServiceError("Inference service returned invalid JSON") from exc

    async def aclose(self) -> None:
        await self._client.aclose()


_client: InferenceServiceClient | None = None


def get_inference_service_client() -> InferenceServiceClient:
    global _client
    if _client is None:
        _client = InferenceServiceClient()
    return _client


async def close_inference_service_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


__all__ = [
    "InferenceServiceClient",
    "InferenceServiceError",
    "InferenceServiceTimeout",
    "InferenceServiceUnavailable",
    "RemoteResponse",
    "close_inference_service_client",
    "get_inference_service_client",
]
