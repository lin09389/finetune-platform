"""
Logging configuration module
"""
import logging
import sys
from pathlib import Path

from pythonjsonlogger.jsonlogger import JsonFormatter


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
            '%(timestamp)s %(level)s %(name)s %(message)s'
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
