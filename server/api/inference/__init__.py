"""推理模块 - 参考 Ollama server 设计模式

This package no longer eagerly imports its route/scheduler submodules so that
``api.inference.facade`` can be registered without pulling in the native runtime
when the application is running in ``service`` mode.
"""

__all__: list[str] = []
