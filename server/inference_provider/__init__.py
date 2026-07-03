"""HTTP provider boundary for the isolated local inference service."""

from .client import (
    InferenceServiceClient,
    InferenceServiceError,
    InferenceServiceTimeout,
    InferenceServiceUnavailable,
    close_inference_service_client,
    get_inference_service_client,
)

__all__ = [
    "InferenceServiceClient",
    "InferenceServiceError",
    "InferenceServiceTimeout",
    "InferenceServiceUnavailable",
    "close_inference_service_client",
    "get_inference_service_client",
]
