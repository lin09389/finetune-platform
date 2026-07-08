from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _pyproject() -> dict:
    return tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def _normalized_names(requirements_file: str) -> set[str]:
    names: set[str] = set()
    for line in (REPO_ROOT / "server" / requirements_file).read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("--"):
            continue
        match = re.match(r"([A-Za-z0-9_.-]+)", stripped)
        if match:
            names.add(match.group(1).lower().replace("_", "-"))
    return names


def _dependency_name(requirement: str) -> str:
    match = re.match(r"\s*([A-Za-z0-9_.-]+)", requirement)
    assert match is not None
    return match.group(1).lower().replace("_", "-")


def test_optional_dependency_profiles_define_runtime_ownership():
    project = _pyproject()["project"]
    base = {_dependency_name(item) for item in project["dependencies"]}
    extras = project["optional-dependencies"]

    assert {"agent", "rag", "cua", "modelhub", "model-ops", "training", "inference", "gpu", "all"} <= set(extras)
    assert {"fastapi", "uvicorn", "httpx", "aiosqlite"} <= base

    # The base runtime must stay control-plane/common only. Heavy execution
    # stacks are owned by explicit extras.
    assert not {
        "torch",
        "transformers",
        "peft",
        "datasets",
        "llama-cpp-python",
        "chromadb",
        "sentence-transformers",
        "pynput",
    } & base

    def names(extra: str) -> set[str]:
        return {_dependency_name(item) for item in extras[extra]}

    assert {"deepagents", "langgraph", "langgraph-checkpoint-sqlite"} <= names("agent")
    assert {"chromadb", "sentence-transformers", "torch"} <= names("rag")
    assert {"pynput", "pyautogui", "rapidocr-onnxruntime"} <= names("cua")
    assert {"huggingface-hub", "modelscope"} <= names("modelhub")
    assert {"torch", "transformers", "peft", "onnx", "onnxruntime"} <= names("model-ops")
    assert {"torch", "transformers", "peft", "datasets", "modelscope"} <= names("training")
    assert {"torch", "transformers", "peft", "llama-cpp-python", "grpcio"} <= names("inference")
    assert {"bitsandbytes"} <= names("gpu")
    assert {"deepagents", "chromadb", "pynput", "modelscope", "peft", "datasets", "llama-cpp-python", "bitsandbytes"} <= names("all")


def test_compose_builds_distinct_backend_dependency_profiles():
    compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert (
        'dockerfile: Dockerfile\n      args:\n        UV_EXTRAS: "--extra agent --extra rag --extra cua --extra modelhub --extra model-ops"'
        in compose
    )
    assert 'dockerfile: Dockerfile.gpu\n      args:\n        UV_EXTRAS: "--extra training --extra gpu"' in compose
    assert 'dockerfile: Dockerfile.gpu\n      args:\n        UV_EXTRAS: "--extra inference"' in compose


def test_requirements_exports_match_runtime_boundaries():
    api = _normalized_names("requirements-api.txt")
    training = _normalized_names("requirements-training.txt")
    inference = _normalized_names("requirements-inference.txt")
    full = _normalized_names("requirements.txt")

    assert {"deepagents", "chromadb", "sentence-transformers", "pynput", "modelscope", "peft", "onnx"} <= api
    assert {"torch", "transformers"} <= api  # local RAG embedding still pulls Torch.
    assert not {"datasets", "llama-cpp-python", "grpcio-tools", "bitsandbytes"} & api

    assert {"torch", "transformers", "peft", "datasets", "modelscope", "bitsandbytes"} <= training
    assert not {"deepagents", "chromadb", "sentence-transformers", "pynput", "llama-cpp-python"} & training

    assert {"torch", "transformers", "peft", "llama-cpp-python", "grpcio-tools"} <= inference
    assert not {"deepagents", "chromadb", "sentence-transformers", "pynput", "datasets", "modelscope", "bitsandbytes"} & inference

    assert api | training | inference <= full


def test_requirements_headers_document_export_commands():
    expected = {
        "requirements.txt": "uv export --extra all --no-dev --no-hashes --format requirements-txt -o server/requirements.txt",
        "requirements-api.txt": "uv export --extra agent --extra rag --extra cua --extra modelhub --extra model-ops --no-dev --no-hashes --format requirements-txt -o server/requirements-api.txt",
        "requirements-training.txt": "uv export --extra training --extra gpu --no-dev --no-hashes --format requirements-txt -o server/requirements-training.txt",
        "requirements-inference.txt": "uv export --extra inference --no-dev --no-hashes --format requirements-txt -o server/requirements-inference.txt",
    }
    for filename, command in expected.items():
        header = "\n".join((REPO_ROOT / "server" / filename).read_text(encoding="utf-8").splitlines()[:2])
        assert command in header
