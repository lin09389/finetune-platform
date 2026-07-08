# Backend dependency profiles

Phase 4 keeps a single repository and a single `uv.lock`, but backend processes
no longer have to install the same dependency set.

## Local development

For the historical all-in-one local setup, install everything:

```bash
uv sync --frozen --extra all --extra dev
```

Start the three backend processes:

```bash
uv run --extra all python -m server.inference_server
uv run --extra all python -m server.training_worker
uv run --extra all python -m uvicorn server.main:app --host 127.0.0.1 --port 8010
```

Windows launchers use those all-in-one extras automatically, except the
single-purpose launchers:

```bash
start-inference-service.bat  # --extra inference
start-training-worker.bat    # --extra training --extra gpu
```

## Docker profiles

| Compose service | Dockerfile | Extras |
| --- | --- | --- |
| `api` | `Dockerfile` | `--extra agent --extra rag --extra cua --extra modelhub --extra model-ops` |
| `training-worker` | `Dockerfile.gpu` | `--extra training --extra gpu` |
| `inference-service` | `Dockerfile.gpu` | `--extra inference` |

The API image intentionally keeps `rag` and `cua` today to preserve the current
combined API surface. It also keeps `modelhub` and `model-ops` because current
model catalog, merge, quantization, and export routes still execute inside the
API process. It does not install worker-only dependencies such as datasets,
llama-cpp-python, gRPC tools, or bitsandbytes.

Important caveat: `rag` includes `sentence-transformers`, which depends on
PyTorch. If the next goal is a completely Torch-free API image, move embeddings
behind a remote Provider or separate embedding service first.

## Pip-compatible exports

`uv` remains the source of truth. Regenerate requirements files from the
repository root:

```bash
uv export --extra all --no-dev --no-hashes --format requirements-txt -o server/requirements.txt
uv export --extra agent --extra rag --extra cua --extra modelhub --extra model-ops --no-dev --no-hashes --format requirements-txt -o server/requirements-api.txt
uv export --extra training --extra gpu --no-dev --no-hashes --format requirements-txt -o server/requirements-training.txt
uv export --extra inference --no-dev --no-hashes --format requirements-txt -o server/requirements-inference.txt
```

Use cases:

- `server/requirements.txt`: full compatibility environment;
- `server/requirements-api.txt`: public API/control-plane image;
- `server/requirements-training.txt`: training worker image;
- `server/requirements-inference.txt`: local inference service image.

Do not hand-edit generated requirements files.

## Ownership map

| Dependency family | Profile |
| --- | --- |
| FastAPI, auth, storage, parsing, HTTP, logging | base dependencies |
| DeepAgents, LangGraph, LangChain | `agent` |
| ChromaDB, sentence-transformers, table store | `rag` |
| screen/mouse/keyboard/OCR drivers | `cua` |
| ModelScope/HuggingFace catalog and download | `modelhub` |
| model merge, quantization, and export routes | `model-ops` |
| PyTorch training, Transformers, PEFT, datasets, export | `training` |
| PyTorch inference, Transformers, PEFT, llama.cpp, gRPC | `inference` |
| bitsandbytes and GPU add-ons | `gpu` |
