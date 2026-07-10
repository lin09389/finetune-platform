# Finetune Platform 2.1

English | [简体中文](README.md)

A local LLM fine-tuning workbench for independent developers and small teams. It brings dataset management, LoRA/QLoRA training, evaluation, inference, deployment packaging, Agent Workbench, project context, memory, and knowledge base features into one product optimized for consumer GPUs.

![Python](https://img.shields.io/badge/Python-3.11-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.109-009688)
![React](https://img.shields.io/badge/React-18-61DAFB)
![Vite](https://img.shields.io/badge/Vite-5-646CFF)
![DeepAgents](https://img.shields.io/badge/DeepAgents-0.6-orange)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

## What It Is

Finetune Platform is not just a collection of training scripts. It is a practical local AI workbench built around the full loop: prepare data, fine-tune a compact model, evaluate results, package deployment artifacts, and let an Agent help with project work.

It is useful when you want to:

- Run LoRA/QLoRA experiments on consumer NVIDIA GPUs with 4GB+ VRAM.
- Manage local models, datasets, training history, evaluation records, and deployment outputs.
- Use one Web UI for inference testing, knowledge base Q&A, model downloads, and workspace management.
- Work with an Agent Workbench that can read project context, plan tasks, execute work, and request approval for sensitive operations.
- Study engineering patterns for local AI platforms, RAG, Agent Session, MCP, CUA, and related integrations.

## Capability Tiers

The backend `GET /api/info` endpoint is the source of truth for capability tiers.

| Tier | Capabilities | Stability |
| --- | --- | --- |
| GA | device, models, datasets, training, inference, chat_sessions, knowledge_base | Core flows intended for daily use and regression coverage |
| Beta | project_context, memory, model_center, workspace | Usable, but APIs and UI may still evolve |
| Experimental | cua, heartbeat, mcp, gateway, ocr_fallbacks, action_recorder | Exploration area for research and extension work |

## Core Features

### Fine-Tuning and Inference

- Model management: local model listing, download, deletion, export, and ModelScope/HuggingFace integration.
- Dataset management: upload, parsing, preprocessing, and training data preparation.
- LoRA/QLoRA training: optimized for low-VRAM machines, with task state, training history, and checkpoint resume.
- Real-time training progress: SSE-based event stream for loss, step, status, and logs.
- Evaluation and comparison: model evaluation, human scoring, history comparison, and pre-deployment checks.
- Multiple inference backends: HuggingFace, Ollama, llama.cpp, vLLM, and environment-based backend switching.
- Deployment packaging: adapters, inference examples, Ollama Modelfile, environment templates, and related artifacts.

### Agent and Workbench

- `/agent` is the default entry and opens the immersive Agent Workbench.
- Agent Session manages lifecycle, events, status, and output parts through FastAPI and SSE.
- New tasks first confirm a Workspace, then select `Build`, `Train`, or `Hybrid`; the Workspace ID and validated project path are persisted with the session.
- The Workbench does not submit a Build/Train/Hybrid task until its Workspace is confirmed. File, command, and training side effects are rooted in that session Workspace, while the timeline shows only its label rather than an absolute path.
- Existing `POST /agent-sessions` clients may still send only `project_path`, and stored sessions remain readable without migration.
- DeepAgents powers execution, with the project mounted as a virtual `/workspace/`.
- Human-in-the-loop approval is supported for sensitive writes, tool calls, and actions before background resume.
- Built-in Build, Explore, and Review Agent manifests can be extended with custom definitions.
- Workspace view, terminal events, execution plan, diffs, sub-agent status, and artifacts are presented in one interface.

### Knowledge, Context, and Memory

- RAG knowledge base: ChromaDB + sentence-transformers, with document parsing, chunking, retrieval, and Q&A.
- Project context: scans local projects, extracts code symbols, and builds context packs.
- Memory system: short-term, mid-term, and long-term memory for chat and Agent tasks.
- File parsing: PDF, DOCX, XLSX, OCR, and other common inputs.

## Tech Stack

| Layer | Technologies |
| --- | --- |
| Backend | FastAPI, Python 3.11, Pydantic, SQLite, PyTorch, Transformers, PEFT |
| Frontend | React 18, TypeScript, Vite, Ant Design, Zustand, Framer Motion |
| Agent | DeepAgents, LangGraph, SSE, virtual workspace, HITL approval |
| RAG | ChromaDB, sentence-transformers, pdfplumber, python-docx, openpyxl |
| Deployment | Docker Compose, optional Electron desktop wrapper, Ollama profile, GPU compose override |

## Quick Start

### Requirements

- Python 3.11.x
- Node.js 18+
- Git
- NVIDIA GPU + CUDA environment, recommended for training and local inference
- Docker Desktop, optional

VRAM guidance:

| VRAM | Suitable Models | Suggested Mode |
| --- | --- | --- |
| 4GB | 0.5B-1.5B INT4 | QLoRA, small batch, short sequence |
| 6GB | 1.5B-3B INT4 | QLoRA |
| 8GB | 3B-7B INT4 | QLoRA or lightweight LoRA |
| 12GB+ | 7B/13B | More comfortable LoRA/QLoRA |

### Windows One-Click Start

Run from the repository root:

```bat
start.bat
```

The script checks the Python/Node environment, installs required dependencies, and starts:

- Frontend: http://127.0.0.1:5173
- Backend: http://127.0.0.1:8010
- Swagger: http://127.0.0.1:8010/docs
- Health check: http://127.0.0.1:8010/health

To verify the environment first:

```bat
verify.bat
```

To install the GPU PyTorch stack for NVIDIA GPUs:

```bat
install-pytorch-gpu.bat
```

### Manual Start

Backend dependencies are best managed with `uv`:

```bash
git clone https://github.com/lin09389/finetune-platform.git
cd finetune-platform
cp .env.example .env

uv sync
```

Start the backend:

```bash
cd server
python -m uvicorn main:app --host 127.0.0.1 --port 8010 --reload
```

Start the frontend:

```bash
cd client
npm install
npm run dev
```

The frontend dev server uses port `5173` and talks directly to `http://127.0.0.1:8010`; it does not rely on a Vite proxy.

### Docker

Start only the API:

```bash
docker compose up -d api
```

Start the development stack:

```bash
docker compose --profile dev up -d
```

Start Ollama:

```bash
docker compose --profile ollama up -d
```

Start with the GPU override:

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
```

View logs:

```bash
docker compose logs -f api
```

## Common Commands

### Backend

```bash
cd server
python -m uvicorn main:app --host 127.0.0.1 --port 8010 --reload
python -m pytest
python -m pytest -m "not integration and not e2e"
python -m pytest -m integration
python -m pytest --cov=server --cov-report=html
```

### Frontend

```bash
cd client
npm run dev
npm run build
npm run typecheck
npm run lint
npm run test:smoke
npm run test:runtime
```

Note: `npm test` runs Vitest in watch mode. For CI or one-off checks, use `npx vitest run` or the targeted scripts above.

### Dependency Management

```bash
uv sync
uv lock
uv export --no-dev --no-hashes --format requirements-txt -o server/requirements.txt
```

`server/requirements.txt` is generated by `uv export`; avoid editing it manually.

## Main Pages

| Route | Page |
| --- | --- |
| `/agent` | Agent Workbench, default entry |
| `/dashboard` | Platform overview |
| `/device` | Device and VRAM monitoring |
| `/models` | Model runtime center (list / download / readiness) |
| `/datasets` | Dataset management |
| `/training` | Training tasks |
| `/chat` | Chat-only interface |
| `/knowledge` | Knowledge base |
| `/inference` | Inference testing |
| `/evaluation` | Model evaluation |
| `/deployment` | Deployment packages |
| `/workspace` | Workspace management |
| `/memory` | Memory system |
| `/modelhub` | Legacy redirect → `/models` |
| `/project-context` | Project context |
| `/mcp`, `/gateway`, `/heartbeat`, `/cua-control` | Experimental capabilities |

## Key APIs

| API | Description |
| --- | --- |
| `GET /health` | Service health check |
| `GET /api/info` | API metadata and capability tiers |
| `GET /device` | Device information |
| `GET /models` | Model management |
| `GET /datasets` | Dataset management |
| `POST /training/start` | Start training |
| `GET /training/progress/stream` | Training progress SSE |
| `POST /inference/*` | Inference service |
| `GET /chat/sessions` | Chat sessions |
| `POST /agent-sessions` | Create an Agent Session; new tasks may include `workspace_id` and `task_mode` (`build` / `train` / `hybrid`) |
| `POST /agent-sessions/{id}/prompt` | Send a task to an Agent Session |
| `GET /agent-sessions/{id}/events/stream` | Agent event SSE |
| `POST /agent-permissions/{permission_id}/approve` | Approve an Agent permission request |
| `POST /agent-permissions/{permission_id}/reject` | Reject an Agent permission request |

## Project Structure

```text
finetune-platform/
├── server/                 # FastAPI backend
│   ├── api/                # Route layer
│   ├── agent_session/      # Agent Session and DeepAgents runtime
│   ├── core/               # Config, storage, training state, event bus
│   ├── training_engine/    # Fine-tuning pipeline
│   ├── inference_service/  # Inference service layer
│   ├── rag/                # RAG knowledge base
│   ├── memory/             # Memory system
│   ├── context/            # Project context
│   ├── workspace/          # File and task APIs
│   └── tests/              # Backend test suite
├── client/                 # React frontend
│   └── src/
│       ├── agent/          # Agent Workbench
│       ├── pages/          # Pages
│       ├── components/     # Shared components
│       ├── services/       # API clients
│       └── test/           # Vitest tests
├── electron/               # Optional desktop wrapper
├── docs/                   # Design, migration, deployment, and capability docs
├── scripts/                # Utility scripts
├── models/                 # Local model directory
├── datasets/               # Dataset directory
├── outputs/                # Training outputs
└── workspaces/             # Runtime workspace data
```

## Configuration

Copy `.env.example` to `.env` and adjust as needed. Common variables:

| Variable | Purpose |
| --- | --- |
| `HOST`, `PORT` | Backend bind address and port |
| `ALLOWED_ORIGINS` | CORS allowlist |
| `INFERENCE_ENGINE` | Inference backend selection |
| `OLLAMA_BASE_URL` | Ollama service URL |
| `HF_MIRROR` | HuggingFace mirror |
| `MAX_CONCURRENT_TRAINING` | Maximum concurrent training jobs |
| `MAX_UPLOAD_SIZE` | Upload size limit |
| `ENABLE_AUTH`, `JWT_SECRET_KEY` | Optional authentication settings |
| `LOG_LEVEL`, `LOG_FORMAT` | Logging level and format |

## Documentation

- [AGENTS.md](AGENTS.md): current project structure, development commands, and capability boundaries.
- [docs/agent_system_design.md](docs/agent_system_design.md): Agent system design.
- [docs/agent_session_migration.md](docs/agent_session_migration.md): Agent Session migration notes.
- [docs/capability-truth-table.md](docs/capability-truth-table.md): capability maturity and dependencies.
- [docs/local-inference-deployment.md](docs/local-inference-deployment.md): local inference deployment notes.
- [docs/MCP_INTEGRATION.md](docs/MCP_INTEGRATION.md): MCP integration.
- [docs/CUA_USAGE.md](docs/CUA_USAGE.md): CUA usage.

## Development Notes

- Backend dependency truth source: root `pyproject.toml` and `uv.lock`.
- Frontend API base URL defaults to `http://127.0.0.1:8010`.
- Formal backend tests mainly live under `server/tests/`; scattered root scripts are mostly debugging helpers.
- Changes to GA capabilities should include or update regression tests.
- Experimental capabilities can move quickly, but README and `/api/info` should stay honest and aligned.

## Current Status

The project is under active development. Training, inference, model/dataset management, knowledge base, chat, and Agent Session have formed the main usable flow. CUA, MCP, Gateway, Heartbeat, and related modules are still experimental and are best treated as research and extension areas.

## Acknowledgements

This project builds on FastAPI, React, Ant Design, PyTorch, Transformers, PEFT, DeepAgents, LangGraph, ChromaDB, Ollama, and the broader open-source AI ecosystem.
