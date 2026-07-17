# Finetune Platform

English | [简体中文](README.md)

**A local-first personal AI Engineer that builds software and trains models from one desktop workbench.**

![Python](https://img.shields.io/badge/Python-3.11-blue)
![Electron](https://img.shields.io/badge/Desktop-Electron-47848F)
![DeepAgents](https://img.shields.io/badge/Agent-DeepAgents-orange)
![Local First](https://img.shields.io/badge/Data-Local--first-2E8B57)
![Windows First](https://img.shields.io/badge/Release-Windows--first-0078D4)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

Finetune Platform is evolving from an LLM fine-tuning console into a personal AI Engineer application for independent developers. You can give it a coding task and let it understand a repository, edit files, run verification, and present evidence. The same Agent can inspect data and hardware, propose a training plan, launch an approved fine-tuning job, follow its progress, and evaluate the resulting model.

Code, models, datasets, sessions, execution traces, and training artifacts stay on your machine by default. SQLite, local files, and local GPUs are first-class. PostgreSQL, Redis, and remote workers belong to a future optional team edition, not the personal runtime.

> **Current stage: active development / source preview.** Electron is the formal desktop runtime boundary and the managed Python foundation is implemented. Production runtime packs, a signed installer, automatic updates, and clean-machine release acceptance are still roadmap work. A repository build is not yet a stable desktop release.

## Product Promise

> On your own computer, projects, and models, one Agent can perform both software and model engineering while every action remains understandable, approvable, recoverable, and measurable.

```mermaid
flowchart LR
    U["Task input"] --> W["Agent Workbench"]
    W --> S["Agent Session"]
    S --> D["DeepAgents execution harness"]
    D --> P["Tool policy and runtime"]
    P --> C["Coding: files · terminal · Git · tests"]
    P --> T["Training: data · models · jobs · evaluation"]
    S --> E["Durable events and evidence"]
    E --> UI["Timeline · diffs · approvals · diagnostics"]
    E -. "roadmap" .-> TT["Trace-to-Train flywheel"]
```

One task can run in four modes:

- **Build:** understand a repository, implement or repair code, run tests, and deliver a diff.
- **Train:** inspect data and VRAM, propose a configuration, launch an approved job, and track results.
- **Hybrid:** change training code, verify preprocessing, run a small experiment, and compare evaluations.

## Why It Is More Than Another Coding Agent

| Typical Coding Agent | Finetune Platform direction |
|---|---|
| Edits code and runs commands | Adds controlled dataset, training, evaluation, and local inference tools to the coding loop |
| Often assumes cloud models or remote sandboxes | Treats local models, GPUs, and user-owned data as formal product paths |
| Delivers when a chat ends | Persists plans, events, diffs, approvals, verification, and artifacts across refresh and restart |
| Only consumes model capability | Aims to turn reviewed Agent trajectories into governed local fine-tuning data |

The long-term loop is:

```text
Coding / Training Task
        → structured execution trajectory
        → evaluation and user feedback
        → versioned candidate dataset
        → LoRA / QLoRA
        → fixed Agent evaluation
        → local model deployment
```

Trace-to-Train is roadmap work, not a currently released feature.

## What Exists Today

### Coding Agent Workbench

- `/agent` is the default entry, combining task input, conversation, plan, timeline, and context.
- Workspace is the long-lived boundary; Build, Train, and Hybrid sessions persist their workspace and mode.
- `AgentSessionService` is the only Agent lifecycle owner, and DeepAgents is the only production tool loop.
- Execution plans, file operations, terminal activity, durable diffs, verification evidence, and recovery are integrated.
- HITL interrupt/resume allows sensitive work to wait for approval and continue in the background.
- Built-in Build, Explore, and Review manifests support async subagents and durable status projections.
- Agent Eval v1 provides versioned scenarios, deterministic regression, and an explicit opt-in real-model path.

### Model Training Assistant

- Local model, dataset, training, evaluation, and deployment-artifact management.
- LoRA/QLoRA, low-VRAM profiles, a durable queue, an isolated Training Worker, and checkpoint recovery.
- Read-only Agent training proposals with model/dataset resolution, validation, and VRAM estimation.
- Training submission passes through existing approval boundaries; duplicate, stale, or cross-owner requests fail closed.
- Durable training events project into Workbench and recover after refresh or API restart.
- An isolated inference service supports local backends behind an OpenAI-compatible boundary.

### Local Knowledge and Desktop Runtime

- RAG knowledge base, project context, code-symbol indexing, memory, and common document parsing.
- Electron supervises the local API, Training Worker, and Inference Service lifecycle.
- The renderer consumes versioned narrow IPC and receives neither internal service secrets nor arbitrary host paths.
- Managed Python 3.11 foundations include strict manifests, SHA-256, staging, health probes, atomic activation, and repair.
- User databases, models, outputs, logs, workspaces, and secrets are separated from replaceable application resources.

## Capability Maturity

The runtime source of truth is `GET /api/info`.

| Tier | Capabilities | Meaning |
|---|---|---|
| GA | device, models, datasets, training, inference, chat_sessions, knowledge_base | Compatibility and regression protected core flows |
| Beta | project_context, memory, model_center, workspace, agent_eval, cloud_chat | Product-integrated, but protocols or UX may evolve |
| Experimental | cua, heartbeat, mcp, gateway, ocr_fallbacks, action_recorder | Isolated exploration surfaces, not stable product promises |

Trusted sandboxing, task-scoped Git worktrees, mutation rewind, complex-project context, Trace-to-Train, permissioned extensions, and the production desktop release pipeline remain on the roadmap.

## Architecture Principles

- **One Agent loop:** DeepAgents owns model iteration, tool choice, planning, subagents, and interrupts. The platform does not add a second ReAct loop.
- **Strong session, thin host:** the platform owns cross-turn lifecycle, workspace binding, persistence, approvals, recovery, events, and diagnostics.
- **Deterministic workflow:** application state machines coordinate jobs, artifacts, and idempotency without deciding the next model tool call.
- **Event-driven projections:** UI, evaluation, diagnostics, automation, and the future Trace Collector consume versioned event facts.
- **Local safety:** file, process, network, secret, and GPU permissions bind to an explicit Workspace, Session, and Runtime.
- **Team-ready interfaces:** domain behavior does not directly depend on SQLite, Redis, or PostgreSQL implementations.

Architecture references:

- [Phase 11+ roadmap](docs/plans/2026-07-13-trusted-local-ai-engineer-roadmap.md)
- [ADR-0001: Agent Session is the primary Agent runtime](docs/adr/0001-agent-session-as-primary-agent-runtime.md)
- [ADR-0011: Keep DeepAgents as the only Agent loop](docs/adr/0011-keep-deepagents-as-the-only-agent-loop.md)

## Quick Start

### Requirements

- Windows 10/11 for the current desktop release target; Linux and macOS remain development-oriented
- Python `>=3.11,<3.12`
- Node.js 18+
- Git
- NVIDIA GPU + CUDA recommended for training and local GPU inference
- `uv` as the recommended Python dependency manager

### Windows Source Start

From the repository root:

```bat
start.bat
```

Check the environment first with:

```bat
verify.bat
```

### Full Development Environment

```powershell
git clone https://github.com/lin09389/finetune-platform.git
Set-Location finetune-platform

uv sync --frozen --extra all --extra dev
npm install
Set-Location client
npm install
npm run build
Set-Location ..
```

Start Electron:

```powershell
npm run start
```

Development requires a compatible Python 3.11 environment and dependencies. Use `FINETUNE_PYTHON` to select an interpreter or `FINETUNE_RUNTIME_MANIFEST` / `FINETUNE_RUNTIME_PACK_DIR` to exercise a local runtime pack.

### Process-by-Process Debugging

```powershell
uv run --extra all python -m server.inference_server
uv run --extra all python -m server.training_worker
uv run --extra all python -m uvicorn server.main:app --host 127.0.0.1 --port 8010
```

In another terminal:

```powershell
Set-Location client
npm run dev
```

The renderer uses `127.0.0.1:5173` and talks directly to `127.0.0.1:8010` without a Vite proxy.

### Optional Docker Profiles

```bash
docker compose up -d api
docker compose --profile dev up -d
docker compose --profile ollama up -d
```

The personal desktop path does not require Docker. See [dependency profiles](docs/dependency-profiles.md).

## Common Verification

```powershell
# Backend
python -m pytest server/tests -m "not integration and not e2e" -q

# Frontend
Set-Location client
npm run typecheck
npm run build
npm run test:smoke

# Electron / runtime pack
Set-Location ..
npm run test:desktop
npm run test:runtime-pack
npm run test:package-policy
```

`npm test` is Vitest watch mode. Use `npx vitest run` or a targeted script for one-off checks.

## Repository Map

```text
finetune-platform/
├── electron/                 # Desktop host, supervision, secure IPC, managed Python
├── client/src/agent/         # Default Agent Workbench
├── server/
│   ├── agent_session/        # Single Agent lifecycle and DeepAgents adapter
│   ├── agent_eval/           # Versioned Agent capability evaluation
│   ├── training_worker/      # Durable queue and GPU worker
│   ├── training_engine/      # LoRA/QLoRA pipeline
│   ├── inference_server/     # Isolated local inference service
│   ├── apps/                 # combined / agent / finetune assembly
│   ├── workspace/            # Workspace domain
│   ├── context/              # Project context and indexing
│   ├── rag/                  # Knowledge base
│   └── memory/               # Memory system
├── docs/                     # ADRs, design, operations, and acceptance
├── scripts/desktop/          # Runtime-pack and package policy tools
├── pyproject.toml            # Python dependency source of truth
└── uv.lock                   # Single Python lockfile
```

`models/`, `datasets/`, `outputs/`, `workspaces/`, and `logs/` are runtime data. They are not source architecture and must not be bundled as replaceable application resources.

## Roadmap

| Phase | Outcome |
|---|---|
| 11 | Thin AgentSession host, runtime binding, steering/follow-up, structured compaction, and event spine |
| 12–14 | Trusted execution sandbox, isolated worktrees, mutation ledger, checkpoints, and safe rewind |
| 15 | Complex, multi-file, long-running Coding Agent capability |
| 16 | Integrated Training Copilot and governed Trace-to-Train loop |
| 17 | Hooks, personal automation, and permissioned extensions |
| 18 | Production runtime packs, signed installer, update/rollback, and clean-machine acceptance |
| 19 | Optional PostgreSQL, Redis, object storage, and team governance |

Phase 16 is the approximate completion point for the Coding Agent + training-assistant core loop. Phase 18 is the target for a distributable personal desktop product. The team edition is not a personal-edition completion requirement.

## Current Limitations

- Production Python 3.11 base runtime packs and a signed Windows installer have not completed release acceptance.
- Execution isolation still needs an enforceable, fail-closed Execution Environment Provider.
- Parallel Coding tasks do not yet receive isolated Git worktrees by default.
- Trace-to-Train, public extensions, and team-edition adapters are not complete.
- CUA, MCP, Gateway, and Heartbeat remain Experimental.

## Documentation

- [Capability maturity and dependencies](docs/capability-truth-table.md)
- [Coding Agent engineering loop](docs/coding-agent-engineering-loop.md)
- [Agent Training Foundation](docs/agent-training-foundation.md)
- [Workspace portability ADR](docs/adr/0009-use-versioned-reference-manifests-for-workspace-portability.md)
- [Desktop packaging and data boundaries](docs/desktop-packaging.md)
- [Phase 10 execution record](docs/phase10-execution-2026-07-16.md)

## License and Acknowledgements

Finetune Platform is available under the [MIT License](LICENSE). It builds on FastAPI, React, Electron, PyTorch, Transformers, PEFT, DeepAgents, LangGraph, ChromaDB, Ollama, and the broader open-source AI ecosystem.
