# ADR-0004: Split runtime dependency profiles and backend images

Date: 2026-07-07

## Status

Accepted.

## Context

Phases 1-3 split the backend along the real failure boundary:

- control-plane API remains the single public entry point;
- training runs in `server.training_worker`;
- local inference runs in `server.inference_server`.

Before this decision, all backend processes installed the same Python
environment. That kept local development simple, but it also meant the API,
training worker, and inference service all carried training, local inference,
RAG, CUA, export, and GPU dependencies.

The fourth phase needs dependency and image isolation without changing the
frontend base URL, splitting the repository, or introducing Kubernetes, Redis,
Kafka, or a second database.

## Decision

Keep one repository and one lockfile, but define explicit optional dependency
profiles in `pyproject.toml`:

| Profile | Owner | Purpose |
| --- | --- | --- |
| base `dependencies` | all backend processes | FastAPI, storage, security, parsing, HTTP, logging, and shared utilities |
| `agent` | API / Agent control plane | DeepAgents, LangGraph, LangChain runtime |
| `rag` | API / Knowledge | ChromaDB, local sentence-transformers embedding, table store |
| `cua` | API / experimental CUA | screen, mouse, keyboard, OCR drivers |
| `modelhub` | API / Model Center | ModelScope and HuggingFace catalog/download integrations |
| `model-ops` | API / Models | existing merge, quantization, conversion, and export routes |
| `training` | training worker | PyTorch, Transformers, PEFT, datasets, model export, ModelScope |
| `inference` | local inference service | PyTorch, Transformers, PEFT, llama.cpp, Ollama HTTP client, gRPC |
| `gpu` | training worker | optional GPU-only add-ons such as bitsandbytes |
| `all` | local compatibility | everything needed by the historical all-in-one developer environment |

Docker Compose now builds different backend dependency sets:

- `api`: `Dockerfile` with `--extra agent --extra rag --extra cua --extra modelhub --extra model-ops`;
- `training-worker`: `Dockerfile.gpu` with `--extra training --extra gpu`;
- `inference-service`: `Dockerfile.gpu` with `--extra inference`.

The exported requirements files mirror those profiles:

- `server/requirements.txt` remains the full compatibility export;
- `server/requirements-api.txt` is for the public API container;
- `server/requirements-training.txt` is for the training worker;
- `server/requirements-inference.txt` is for the inference service.

Windows local launchers use `--extra all` for the one-machine development
experience. Single-purpose launchers use the smallest matching profile when
safe.

## Consequences

### Positive

- Training and inference containers no longer install Agent, CUA, Knowledge,
  or workspace dependencies.
- The API container no longer installs worker-only training/inference packages
  such as datasets, llama-cpp-python, gRPC tools, or bitsandbytes. It still
  installs `model-ops` because current model merge/export routes execute in the
  API process.
- Deployment requirements are generated from the same `pyproject.toml` and
  `uv.lock`, so Docker, uv, and pip-compatible environments share one source of
  truth.
- Phase 4 stays operationally small: no database split, no message broker, no
  orchestration platform.

### Trade-offs

- The API image is not fully Torch-free while local Knowledge/RAG uses
  `sentence-transformers`; that package depends on PyTorch. A Torch-free Agent
  image requires a later embedding Provider or standalone embedding service.
- CUA is still installed in the default API image because the current CUA router
  imports screen/input/OCR dependencies during app assembly. Making CUA a truly
  optional API image feature requires lazy router/module imports as a later
  cleanup.
- Model merge/export operations still run in the API process, so `model-ops`
  remains in the API image. Moving these operations to a worker is a later
  execution-plane cleanup.
- There is still one lockfile. This is intentional: separate lockfiles would
  add upgrade and compatibility overhead before the runtime units need
  independent release cadences.

## Failure modes and mitigations

- **Wrong local command misses extras**: Windows start scripts call `uv sync` or
  `uv run` with `--extra all`; profile-specific scripts document their own
  extras.
- **Docker profile drift**: tests assert Compose build args and requirements
  exports match the dependency profiles.
- **Hidden API Torch dependency**: the `rag` profile documents the
  `sentence-transformers -> torch` edge explicitly.
- **Worker imports control-plane-only packages**: profile boundary tests reject
  Agent/RAG/CUA packages in training and inference requirements.

## Alternatives considered

1. **Keep one all-inclusive backend image**  
   Operationally simple, but fails the phase-4 goal of dependency and image
   isolation.

2. **Split into multiple repositories or lockfiles now**  
   Too much process overhead for a student/independent-developer project and
   not required by the current single-machine deployment model.

3. **Make API Torch-free immediately**  
   Desirable, but it requires changing the embedding architecture. That is a
   separate execution-plane decision, not a dependency packaging change.

## Verification

Phase 4 is considered valid only when:

- `uv lock` succeeds;
- the four requirements exports are regenerated from `uv`;
- Docker Compose config resolves;
- tests verify pyproject profile ownership, Compose build extras, and
  requirements boundary expectations;
- phase 1-3 regression tests still pass.
