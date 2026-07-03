"""Durable single-machine training worker.

The backend historically imports ``core`` and ``api`` as top-level packages.
Preserve that contract when launched from the repository root with
``python -m server.training_worker``.
"""

import sys
from pathlib import Path

_SERVER_DIR = Path(__file__).resolve().parent.parent
if str(_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVER_DIR))

from .repository import TrainingEventRepositoryHub, TrainingJob, TrainingJobRepository  # noqa: E402

__all__ = ["TrainingEventRepositoryHub", "TrainingJob", "TrainingJobRepository"]
