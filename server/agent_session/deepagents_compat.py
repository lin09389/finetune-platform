from __future__ import annotations

from typing import Any


def patch_torch_pytree_for_transformers() -> None:
    """Bridge torch 2.1.x with newer transformers imports used by LangChain."""

    try:
        import torch

        pytree = torch.utils._pytree
        if hasattr(pytree, "register_pytree_node") or not hasattr(pytree, "_register_pytree_node"):
            return

        def register_pytree_node(typ: Any, flatten_fn: Any, unflatten_fn: Any, **kwargs: Any) -> None:
            supported = {
                key: value
                for key, value in kwargs.items()
                if key in {"to_dumpable_context", "from_dumpable_context"}
            }
            pytree._register_pytree_node(typ, flatten_fn, unflatten_fn, **supported)

        pytree.register_pytree_node = register_pytree_node
    except Exception:
        return


__all__ = ["patch_torch_pytree_for_transformers"]
