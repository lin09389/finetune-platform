"""本地推理 gRPC 服务骨架。"""
from __future__ import annotations

import json
import logging
from typing import Any

from inference_service.service import get_local_inference_service
from inference_service.types import LocalInferenceRequest

logger = logging.getLogger(__name__)

try:
    import grpc

    HAS_GRPC = True
except ImportError:  # pragma: no cover - optional dependency
    grpc = None
    HAS_GRPC = False


class LocalInferenceGrpcServer:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self._server = None

    async def start(self) -> bool:
        if not HAS_GRPC:
            logger.warning("gRPC 未安装，跳过本地推理 gRPC 服务启动")
            return False

        if self._server is not None:
            return True

        service = get_local_inference_service()
        self._server = grpc.aio.server()
        self._server.add_generic_rpc_handlers(
            (
                grpc.method_handlers_generic_handler(
                    "localinference.LocalInference",
                    {
                        "Generate": grpc.unary_unary_rpc_method_handler(
                            lambda request, context: _json_unary_handler(service, request),
                            request_deserializer=lambda payload: json.loads(payload.decode("utf-8")),
                            response_serializer=lambda payload: json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                        ),
                        "Chat": grpc.unary_unary_rpc_method_handler(
                            lambda request, context: _json_unary_handler(service, request),
                            request_deserializer=lambda payload: json.loads(payload.decode("utf-8")),
                            response_serializer=lambda payload: json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                        ),
                        "GenerateStream": grpc.unary_stream_rpc_method_handler(
                            lambda request, context: _json_stream_handler(service, request),
                            request_deserializer=lambda payload: json.loads(payload.decode("utf-8")),
                            response_serializer=lambda payload: json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                        ),
                    },
                ),
            )
        )
        self._server.add_insecure_port(f"{self.host}:{self.port}")
        await self._server.start()
        logger.info("本地推理 gRPC 服务已启动 %s:%s", self.host, self.port)
        return True

    async def stop(self) -> None:
        if self._server is None:
            return
        await self._server.stop(grace=2.0)
        self._server = None


async def _json_unary_handler(service, request: dict[str, Any]) -> dict[str, Any]:
    inference_request = LocalInferenceRequest(
        model=request["model"],
        backend=request.get("backend", "huggingface"),
        prompt=request.get("prompt"),
        messages=request.get("messages", []),
        options=request.get("options", {}),
        stream=False,
        request_id=request.get("request_id"),
    )
    response = await service.generate_cached(inference_request)
    return {
        "request_id": response.request_id,
        "backend": response.backend,
        "model": response.model,
        "content": response.content,
        "metadata": response.metadata,
    }


async def _json_stream_handler(service, request: dict[str, Any]):
    inference_request = LocalInferenceRequest(
        model=request["model"],
        backend=request.get("backend", "huggingface"),
        prompt=request.get("prompt"),
        messages=request.get("messages", []),
        options=request.get("options", {}),
        stream=True,
        request_id=request.get("request_id"),
    )
    async for chunk in service.generate_stream(inference_request):
        yield {"chunk": chunk, "request_id": inference_request.request_id}


_grpc_server: LocalInferenceGrpcServer | None = None


def get_inference_grpc_server(host: str, port: int) -> LocalInferenceGrpcServer:
    global _grpc_server
    if _grpc_server is None:
        _grpc_server = LocalInferenceGrpcServer(host=host, port=port)
    return _grpc_server
