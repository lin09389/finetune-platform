from __future__ import annotations

from importlib.metadata import version


def test_fastapi_testclient_dependency_versions_are_the_project_standard():
    assert _version_tuple(version("fastapi")) == (0, 109, 0)
    assert _version_tuple(version("starlette")) == (0, 35, 1)
    assert _version_tuple(version("httpx")) == (0, 28, 1)


def _version_tuple(raw: str) -> tuple[int, int, int]:
    parts = raw.split(".")
    return tuple(int(part) for part in parts[:3])
