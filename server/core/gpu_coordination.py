"""Cross-process GPU coordination MVP (train vs infer).

File-backed lease so training_worker and inference_server (or in-process
training/inference) cannot both blindly claim the same consumer GPU.

Not a perfect distributed lock — best-effort coordination with clear errors.
Disable with GPU_COORDINATION=off outside production/staging only.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

TRAINING_HOLDER = "training"
INFERENCE_HOLDER = "inference"
_DEFAULT_LEASE_NAME = "gpu0"


class GpuCoordinationError(RuntimeError):
    """Raised when GPU work is refused due to an active conflicting lease."""

    def __init__(self, message: str, *, code: str = "gpu_busy"):
        super().__init__(message)
        self.code = code


@dataclass
class GpuLeaseState:
    holder: str | None
    owner: str | None
    acquired_at: float | None
    expires_at: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "holder": self.holder,
            "owner": self.owner,
            "acquired_at": self.acquired_at,
            "expires_at": self.expires_at,
        }


class GpuCoordinator:
    """Simple exclusive lease for train vs infer on a logical GPU id."""

    def __init__(self, path: Path | None = None, *, lease_seconds: float = 3600.0):
        if path is None:
            from core.config import get_settings

            base = get_settings().base_dir / "data"
            base.mkdir(parents=True, exist_ok=True)
            path = base / "gpu_lease.json"
        self.path = Path(path)
        self.lease_seconds = lease_seconds
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> GpuLeaseState:
        if not self.path.exists():
            return GpuLeaseState(None, None, None, None)
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return GpuLeaseState(
                holder=data.get("holder"),
                owner=data.get("owner"),
                acquired_at=data.get("acquired_at"),
                expires_at=data.get("expires_at"),
            )
        except Exception as exc:
            logger.debug("gpu lease read failed: %s", exc)
            return GpuLeaseState(None, None, None, None)

    def _write(self, state: GpuLeaseState) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    def _expired(self, state: GpuLeaseState, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        if state.holder is None:
            return True
        if state.expires_at is None:
            return False
        return now >= float(state.expires_at)

    def get_state(self) -> GpuLeaseState:
        state = self._read()
        if self._expired(state):
            return GpuLeaseState(None, None, None, None)
        return state

    def claim(
        self,
        holder: str,
        *,
        owner: str,
        force: bool = False,
        lease_seconds: float | None = None,
    ) -> GpuLeaseState:
        from security.runtime_policy import gpu_coordination_enabled

        if not gpu_coordination_enabled():
            return GpuLeaseState(holder, owner, time.time(), None)

        now = time.time()
        state = self._read()
        if not self._expired(state, now) and state.holder and state.holder != holder:
            if not force:
                raise GpuCoordinationError(
                    f"GPU leased by {state.holder!r} (owner={state.owner!r}); "
                    f"cannot claim for {holder!r}",
                    code="gpu_lease_conflict",
                )
        ttl = self.lease_seconds if lease_seconds is None else lease_seconds
        new_state = GpuLeaseState(
            holder=holder,
            owner=owner,
            acquired_at=now,
            expires_at=now + ttl,
        )
        self._write(new_state)
        return new_state

    def release(self, holder: str, *, owner: str | None = None) -> None:
        from security.runtime_policy import gpu_coordination_enabled

        if not gpu_coordination_enabled():
            return
        state = self._read()
        if state.holder != holder:
            return
        if owner is not None and state.owner and state.owner != owner:
            return
        self._write(GpuLeaseState(None, None, None, None))

    def assert_inference_allowed(self) -> None:
        from security.runtime_policy import gpu_coordination_enabled

        if not gpu_coordination_enabled():
            return
        state = self.get_state()
        if state.holder == TRAINING_HOLDER:
            raise GpuCoordinationError(
                "Inference model load refused: training holds the GPU lease. "
                "Stop training or wait for the lease to expire.",
                code="gpu_training_active",
            )

    def assert_training_allowed(self) -> None:
        from security.runtime_policy import gpu_coordination_enabled

        if not gpu_coordination_enabled():
            return
        state = self.get_state()
        if state.holder == INFERENCE_HOLDER:
            raise GpuCoordinationError(
                "Training refused: inference holds the GPU lease. "
                "Unload inference models or wait for the lease to expire.",
                code="gpu_inference_active",
            )


_coordinator: GpuCoordinator | None = None


def get_gpu_coordinator() -> GpuCoordinator:
    global _coordinator
    if _coordinator is None:
        _coordinator = GpuCoordinator()
    return _coordinator


def reset_gpu_coordinator(path: Path | None = None) -> GpuCoordinator:
    global _coordinator
    _coordinator = GpuCoordinator(path=path)
    return _coordinator


def claim_training_gpu(owner: str, **kwargs: Any) -> GpuLeaseState:
    return get_gpu_coordinator().claim(TRAINING_HOLDER, owner=owner, **kwargs)


def release_training_gpu(owner: str | None = None) -> None:
    get_gpu_coordinator().release(TRAINING_HOLDER, owner=owner)


def claim_inference_gpu(owner: str, **kwargs: Any) -> GpuLeaseState:
    return get_gpu_coordinator().claim(INFERENCE_HOLDER, owner=owner, **kwargs)


def release_inference_gpu(owner: str | None = None) -> None:
    get_gpu_coordinator().release(INFERENCE_HOLDER, owner=owner)


def assert_inference_gpu_available() -> None:
    get_gpu_coordinator().assert_inference_allowed()


def assert_training_gpu_available() -> None:
    get_gpu_coordinator().assert_training_allowed()
