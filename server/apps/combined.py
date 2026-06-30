"""Backward-compatible combined ASGI entrypoint."""

from .factory import create_application
from .profiles import ApplicationProfile

app = create_application(ApplicationProfile.COMBINED)

__all__ = ["app"]
