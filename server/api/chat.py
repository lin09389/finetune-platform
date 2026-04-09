"""Compatibility shim for chat router.

Canonical implementation is in api.chat.routes.
"""
from api.chat.routes import router

__all__ = ["router"]
