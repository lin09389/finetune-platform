"""Profile-based FastAPI application entrypoints.

The existing backend modules use ``api``/``core`` as top-level packages. Keep
that import contract when an app is launched as ``server.apps.<profile>:app``.
"""

import os
import sys
from pathlib import Path

_SERVER_DIR = Path(__file__).resolve().parent.parent
if str(_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVER_DIR))

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")

from .profiles import ApplicationProfile

__all__ = ["ApplicationProfile"]
