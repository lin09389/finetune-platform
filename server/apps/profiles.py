from __future__ import annotations

from enum import Enum


class ApplicationProfile(str, Enum):
    COMBINED = "combined"
    AGENT = "agent"
    FINETUNE = "finetune"

    @property
    def includes_agent(self) -> bool:
        return self in {ApplicationProfile.COMBINED, ApplicationProfile.AGENT}

    @property
    def includes_finetune(self) -> bool:
        return self in {ApplicationProfile.COMBINED, ApplicationProfile.FINETUNE}


def coerce_profile(value: ApplicationProfile | str) -> ApplicationProfile:
    if isinstance(value, ApplicationProfile):
        return value
    return ApplicationProfile(str(value).strip().lower())


__all__ = ["ApplicationProfile", "coerce_profile"]
