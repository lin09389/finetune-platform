"""Agent Workspace ASGI entrypoint."""

from .factory import create_application
from .profiles import ApplicationProfile

app = create_application(ApplicationProfile.AGENT)

__all__ = ["app"]
