"""
Logging configuration module
"""
import logging
import sys
from pathlib import Path
from typing import Any

from pythonjsonlogger.jsonlogger import JsonFormatter

from core.tracing import get_correlation_id


class CustomJsonFormatter(JsonFormatter):
    """Custom JSON log formatter"""
    pass


def setup_logging(
    log_dir: Path,
    log_level: str = "INFO",
    enable_json: bool = False
) -> logging.Logger:
    """
    Setup logging

    Args:
        log_dir: Log directory
        log_level: Log level
        enable_json: Whether to enable JSON format

    Returns:
        Configured logger instance
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "finetune-platform.log"

    logger = logging.getLogger("finetune-platform")
    logger.setLevel(getattr(logging, log_level.upper()))
    logger.handlers.clear()

    if enable_json:
        formatter = CustomJsonFormatter(
            '%(asctime)s %(levelname)s %(name)s %(message)s'
        )
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def get_logger(name: str = "finetune-platform") -> logging.Logger:
    """Get logger instance"""
    return logging.getLogger(name)


def log_inference_event(logger: logging.Logger, message: str, **fields: Any) -> None:
    """记录结构化推理日志字段。"""
    extra_payload = " ".join(f"{key}={value}" for key, value in fields.items())
    logger.info(f"{message} {extra_payload}".strip())


def log_request_completed(
    logger: logging.Logger,
    *,
    method: str,
    status_code: int,
    duration_ms: float,
    profile: str,
) -> None:
    """Log a completed request with fixed, non-sensitive structured fields.

    Paths, query parameters, account/session identifiers, authorization values,
    request bodies, and prompt text are intentionally not accepted here.
    """

    logger.info(
        "http_request_completed",
        extra={
            "correlation_id": get_correlation_id(),
            "http_method": method,
            "http_status_code": status_code,
            "duration_ms": round(duration_ms, 3),
            "application_profile": profile,
        },
    )
