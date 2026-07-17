"""Transport-neutral contracts for the Native Agent Loop v2.

This package deliberately contains only domain contracts in Wave 0.  Session
ownership, persistence, transports, model calls, and tools are introduced by
later migration waves behind these contracts.
"""

from .contracts import SCHEMA_VERSION

__all__ = ["SCHEMA_VERSION"]
