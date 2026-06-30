"""Finetune and local inference ASGI entrypoint."""

from .factory import create_application
from .profiles import ApplicationProfile

app = create_application(ApplicationProfile.FINETUNE)

__all__ = ["app"]
