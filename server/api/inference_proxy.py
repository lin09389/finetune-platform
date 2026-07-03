"""Control-plane reverse proxy for the isolated inference service."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Any

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from inference_provider.client import (
    InferenceServiceTimeout,
    InferenceServiceUnavailable,
    get_inference_service_client,
)
from inference_provider.fallback import cloud_fallback_response, cloud_fallback_stream

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Inference Provider Proxy"])

_HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
    "authorization",
    "x-lora-adapter",
    "x-model-path",
}
_RESPONSE_HEADERS = {
    "content-type",
    "cache-control",
    "x-accel-buffering",
    "retry-after",
    "x-request-id",
}


def _forward_headers(request: Request) -> dict[str, str]:
    return {
        name: value
        for name, value in request.headers.items()
        if name.lower() not in _HOP_BY_HOP
    }


def _response_headers(headers: dict[str, str]) -> dict[str, str]:
    return {name: value for name, value in headers.items() if name.lower() in _RESPONSE_HEADERS}


def _error_response(status_code: int, message: str, code: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "message": message,
                "type": "server_error",
                "param": None,
                "code": code,
            }
        },
    )


async def _fallback(payload: dict[str, Any], *, stream: bool):
    try:
        if stream:
            iterator = await cloud_fallback_stream(payload)
            if iterator is not None:
                return StreamingResponse(
                    iterator,
                    media_type="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
                )
        else:
            response = await cloud_fallback_response(payload)
            if response is not None:
                return JSONResponse(response)
    except Exception:
        logger.exception("Cloud inference fallback failed")
    return None


async def _non_stream_proxy(request: Request, body: bytes, payload: dict[str, Any] | None = None):
    client = get_inference_service_client()
    try:
        remote = await client.request(
            request.method,
            request.url.path,
            params=request.query_params.multi_items(),
            content=body,
            headers=_forward_headers(request),
        )
    except InferenceServiceTimeout as exc:
        fallback = await _fallback(payload or {}, stream=False) if payload is not None else None
        return fallback or _error_response(504, str(exc), exc.code)
    except InferenceServiceUnavailable as exc:
        fallback = await _fallback(payload or {}, stream=False) if payload is not None else None
        return fallback or _error_response(503, str(exc), exc.code)

    if remote.status_code == 503 and payload is not None:
        fallback = await _fallback(payload, stream=False)
        if fallback is not None:
            return fallback
    return Response(
        content=remote.content,
        status_code=remote.status_code,
        headers=_response_headers(remote.headers),
        media_type=None,
    )


async def _stream_proxy(request: Request, body: bytes, payload: dict[str, Any]):
    client = get_inference_service_client()
    try:
        remote = await client.open_stream(
            request.method,
            request.url.path,
            params=request.query_params.multi_items(),
            content=body,
            headers=_forward_headers(request),
        )
    except InferenceServiceTimeout as exc:
        fallback = await _fallback(payload, stream=True)
        return fallback or _error_response(504, str(exc), exc.code)
    except InferenceServiceUnavailable as exc:
        fallback = await _fallback(payload, stream=True)
        return fallback or _error_response(503, str(exc), exc.code)

    if remote.status_code >= 400:
        content = await remote.aread()
        await remote.aclose()
        if remote.status_code == 503:
            fallback = await _fallback(payload, stream=True)
            if fallback is not None:
                return fallback
        return Response(
            content=content,
            status_code=remote.status_code,
            headers=_response_headers(dict(remote.headers)),
        )

    async def relay() -> AsyncIterator[bytes]:
        try:
            async for chunk in remote.aiter_raw():
                yield chunk
        except httpx.TimeoutException:
            error = {
                "error": {
                    "message": "Local inference stream timed out",
                    "type": "server_error",
                    "param": None,
                    "code": "inference_timeout",
                }
            }
            yield f"data: {json.dumps(error)}\n\n".encode()
        except httpx.TransportError:
            error = {
                "error": {
                    "message": "Local inference stream disconnected",
                    "type": "server_error",
                    "param": None,
                    "code": "inference_service_unavailable",
                }
            }
            yield f"data: {json.dumps(error)}\n\n".encode()
        finally:
            await remote.aclose()

    return StreamingResponse(
        relay(),
        status_code=remote.status_code,
        media_type=remote.headers.get("content-type", "text/event-stream").split(";", 1)[0],
        headers=_response_headers(dict(remote.headers)),
    )


@router.get("/v1/models")
async def proxy_models(request: Request):
    return await _non_stream_proxy(request, b"")


@router.post("/v1/chat/completions")
async def proxy_chat_completions(request: Request):
    body = await request.body()
    try:
        payload = json.loads(body or b"{}")
    except (TypeError, json.JSONDecodeError):
        payload = {}
    if bool(payload.get("stream")):
        return await _stream_proxy(request, body, payload)
    return await _non_stream_proxy(request, body, payload)


_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"]


@router.api_route("/inference", methods=_METHODS)
@router.api_route("/inference/{path:path}", methods=_METHODS)
@router.api_route("/model-runtime", methods=_METHODS)
@router.api_route("/model-runtime/{path:path}", methods=_METHODS)
@router.api_route("/inference-engine", methods=_METHODS)
@router.api_route("/inference-engine/{path:path}", methods=_METHODS)
async def proxy_legacy_inference(request: Request, path: str = ""):
    body = await request.body()
    payload: dict[str, Any] = {}
    if body:
        with suppress(TypeError, json.JSONDecodeError):
            payload = json.loads(body)
    expects_stream = request.url.path.endswith("/stream") or "text/event-stream" in request.headers.get("accept", "")
    if expects_stream:
        return await _stream_proxy(request, body, payload)
    return await _non_stream_proxy(request, body)


@router.get("/inference-service/status")
async def inference_service_status():
    client = get_inference_service_client()
    try:
        health = await client.get_json("/health")
        capabilities = await client.get_json("/internal/capabilities")
        return {"status": "online", "health": health, "capabilities": capabilities}
    except InferenceServiceTimeout as exc:
        return _error_response(504, str(exc), exc.code)
    except InferenceServiceUnavailable as exc:
        return _error_response(503, str(exc), exc.code)


__all__ = ["router"]
