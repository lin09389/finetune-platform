# Finetune Platform 2.0

Enterprise-Ready LLM Fine-Tuning Platform for Consumer GPUs (4GB+ VRAM)

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18+-61dafb.svg)](https://reactjs.org)
[![DeepAgents](https://img.shields.io/badge/DeepAgents-0.6+-orange.svg)](https://github.com/langchain-ai/deepagents)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.2+-orange.svg)](https://github.com/langchain-ai/langgraph)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## What This Project Is

Finetune Platform 2.0 is a local AI workbench for developers who need practical LLM adaptation on affordable hardware. It provides an end-to-end workflow from dataset preparation and LoRA/QLoRA training to evaluation, deployment packaging, and agent-assisted development.

Recommended first run:

1. Upload a small dataset (5-20 examples) in `Datasets`.
2. Start a lightweight LoRA/QLoRA job in `Training` and monitor SSE progress.
3. Compare base vs fine-tuned outputs in `Evaluation`.
4. Export deployment artifacts in `Deployment` (LoRA adapter, Ollama Modelfile, API samples, `.env` template).

## Capability Tiers

| Tier | Scope |
|------|-------|
| **GA** | Training, inference, model/dataset management, chat sessions, core knowledge base |
| **Beta** | Project context, memory, model center, workspace, Agent Session + DeepAgents |
| **Experimental** | CUA, Action Recorder, MCP, Heartbeat, Gateway extension paths |

Experimental pages may be visible but are not considered stable production commitments.

## Core Features

### Product Capabilities
- Low-VRAM tuning optimized for 4GB+ GPUs (`LoRA` / `QLoRA`)
- Model and dataset lifecycle management (HuggingFace + ModelScope)
- Training Monitor V2 with SSE streaming, checkpoint resume, and training history
- Multi-backend inference: HuggingFace / vLLM / LlamaCPP / Ollama
- Unified Chat + Agent workflow with `auto / chat / agent` routing
- DeepAgents runtime with HITL approval/resume flow
- Workspace + Context + Memory integration (ChromaDB + sentence-transformers)
- Document parsing (PDF / DOCX / XLSX / OCR)

### Engineering Capabilities
- SQLite persistence with migrations and periodic backups
- Security layers: WAF checks, JWT auth (optional), rate limiting, audit boundaries
- Structured logging with per-request Trace ID
- Broad test coverage across training, inference, agent session, gateway, and frontend
- Docker Compose profiles (dev/GPU/Ollama) + optional Electron packaging
- Cloud model gateway (`ai.gateway`) with OpenAI-compatible interfaces

## Architecture Overview

The repository has four main surfaces:

- **Finetune Runtime**: models, datasets, training, inference, evaluation, deployment
- **Chat Surface**: chat sessions, streaming messages, context panel, sharing/branching
- **Agent Surface**: intent routing, agent sessions, DeepAgents execution, approval gates
- **Workspace Surface**: project files, context retrieval, local development collaboration

### Backend

```text
server/
├── api/                       # FastAPI routes
├── agent_session/             # Canonical agent runtime (DeepAgents)
├── chat_agent/                # Intent classification only (chat vs agent)
├── training_engine/           # Fine-tuning pipelines
├── inference_service/         # Inference backends and serving
├── context/                   # Project scan/index/retrieval
├── memory/                    # Multi-layer memory
├── rag/                       # ChromaDB + embeddings
├── security/                  # Rate limit, auth, sandbox, guards
├── workspace/                 # Workspace/file/task APIs
├── gateway/                   # Experimental gateway
├── heartbeat/                 # Experimental heartbeat scheduler
└── main.py
```

### Frontend

```text
client/src/
├── pages/                     # Feature pages
├── components/                # Reusable UI
├── services/                  # API client
├── store/                     # Zustand state
├── theme/                     # Motion/theme tokens
└── test/                      # Vitest suites
```

## System Requirements

### Hardware Guidance

| VRAM | Typical Model Range | Training Mode | Notes |
|------|---------------------|---------------|-------|
| 4GB  | 0.5B-1.5B (INT4)    | QLoRA         | Minimum |
| 6GB  | 3B-7B (INT4)        | QLoRA         | Entry |
| 8GB  | 7B (INT4)           | LoRA          | Recommended |
| 12GB | 7B/13B              | LoRA/QLoRA    | Ideal |
| 24GB | 13B/30B             | LoRA          | Professional |

### Software

- Python 3.10+
- Node.js 18+
- CUDA 11.8+ (for NVIDIA acceleration)
- Docker 20.10+ (optional)
- Windows 10/11, Linux, or macOS

## Quick Start

### Option 1: Windows One-Click Startup (Recommended)

Run `start.bat` from the project root. It will:

1. Validate Python/Node environments
2. Install missing backend/frontend dependencies
3. Start backend (`:8010`) and frontend (`:5173`) in separate terminals

Endpoints:
- Frontend: http://localhost:5173
- Swagger API docs: http://localhost:8010/docs
- Health endpoint: http://localhost:8010/health

### Option 2: Manual Startup (Cross-Platform)

```bash
git clone https://github.com/lin09389/finetune-platform.git
cd finetune-platform
cp .env.example .env

cd server
pip install -r requirements.txt
cd ../client
npm install
```

Start services in two terminals:

```bash
# Terminal 1
cd server
python -m uvicorn main:app --host 127.0.0.1 --port 8010
```

```bash
# Terminal 2
cd client
npm run dev
```

### Option 3: Docker

```bash
docker compose up -d --build

docker compose --profile ollama up -d --build

docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
```

View logs:

```bash
docker compose logs -f api frontend
```

## Key API Endpoints

- `GET /health`
- `GET /device/info`
- `POST /training/start`
- `GET /training/v2/events/stream`
- `POST /inference/stream`
- `POST /chat-agent/intent`
- `POST /agent-sessions`
- `POST /agent-sessions/{id}/prompt`
- `GET /agent-sessions/{id}/events/stream`
- `POST /agent-permissions/{permission_id}/decide`

## Development Commands

### Backend

```bash
cd server
python -m uvicorn main:app --host 127.0.0.1 --port 8010 --reload
pytest
pytest -m "not integration and not e2e"
pytest --cov=server --cov-report=html
```

### Frontend

```bash
cd client
npm run dev
npm run build
npm test
npm run typecheck
npm run lint
```

## Testing

```bash
# Backend
cd server
pytest -v

# Frontend
cd client
npm test
npm run test:smoke
```

The repository includes broad automated coverage for agent session lifecycle, training/inference paths, gateway components, and frontend smoke tests.

## Security Highlights

- Path traversal protection for workspace/file operations
- Upload validation (file type, size, and content checks)
- Optional JWT authentication
- Rate limiting and security response headers
- Agent action boundaries via workspace checks + command allowlist
- HITL approval gates for sensitive patch/command actions

## Environment Variables

Common variables (see `.env.example` for full list):

- `HOST`, `PORT`
- `ALLOWED_ORIGINS`
- `INFERENCE_ENGINE` (`huggingface` / `vllm` / `llamacpp` / `ollama`)
- `OLLAMA_BASE_URL`
- `HF_MIRROR`
- `MAX_CONCURRENT_TRAINING`
- `RATE_LIMIT`, `RATE_WINDOW`
- `MAX_UPLOAD_SIZE`
- `ENABLE_AUTH`, `JWT_SECRET_KEY`
- `LOG_LEVEL`, `LOG_FORMAT`

## Project Structure

```text
finetune-platform/
├── server/                   # FastAPI backend
├── client/                   # React + TypeScript frontend
├── electron/                 # Optional desktop wrapper
├── models/                   # Local models
├── datasets/                 # Dataset storage
├── outputs/                  # Training outputs
├── logs/                     # Runtime logs
├── docs/                     # Project documentation
└── scripts/                  # Validation/utility scripts
```

## Documentation

- [AGENTS.md](AGENTS.md): project structure, commands, capability boundaries
- [CLAUDE.md](CLAUDE.md): engineering conventions and constraints
- [Docker Notes](docs/notes/DOCKER.md): container deployment and GPU setup
- [Capability Truth Table](docs/capability-truth-table.md): maturity/dependency/failure modes
- [Agent Session Design](docs/agent_session_migration.md): migration and design history

## Roadmap Note

Finetune Platform is under active iteration. Core tuning and inference flows are available, while several advanced modules are still evolving quickly in Beta/Experimental stages.

## License

MIT

## Acknowledgements

- HuggingFace Transformers
- PEFT
- DeepAgents
- LangGraph
- FastAPI
- React
- Ant Design
- ChromaDB
