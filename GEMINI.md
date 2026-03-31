# Finetune Platform

## Project Overview
This project is an enterprise-enhanced platform designed for fine-tuning Large Language Models (LLMs) specifically optimized for consumer-grade graphics cards (as low as 4GB VRAM). The platform supports INT4 quantization and QLoRA fine-tuning.

It consists of:
- **Backend (server/)**: A FastAPI-based Python server handling ML training, inference, dataset management, and various advanced agentic capabilities like RAG (Retrieval-Augmented Generation), CUA (Computer Use Agent), and MCP (Model Context Protocol).
- **Frontend (client/)**: A React 18 application built with TypeScript, Vite, and Ant Design.
- **Desktop App (electron/)**: An Electron wrapper for deploying the application as a desktop client.

## Building and Running

### Development Mode

You can run the full stack (Frontend + Electron) using the concurrently script in the root directory:
```bash
npm run dev
```

Alternatively, run components individually:

**Backend:**
```bash
cd server
pip install -r requirements.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

**Frontend:**
```bash
cd client
npm install
npm run dev
```

### Docker Deployment
The project includes a `docker-compose.yml` for containerized deployment, which also supports NVIDIA GPU passthrough.

```bash
# Start API only
docker compose up -d api

# Start full stack (API + Frontend)
docker compose --profile dev up -d
```

## Development Conventions

- **Backend:**
  - Built with `FastAPI` (Python 3.10+).
  - Uses `pytest` for testing (run `pytest` in the `server` directory).
  - Code should follow PEP 8 standards, and the project uses structured JSON logging.
  - Dependencies are managed via `requirements.txt`.
- **Frontend:**
  - Built with React, TypeScript, and Vite.
  - Uses `vitest` for testing (run `npm test` in the `client` directory).
  - Uses `eslint` and `prettier` for code formatting.
  - State management uses `zustand`.
- **Advanced Features:**
  - **CUA (Computer Use Agent):** Provides screen capture, mouse/keyboard control, and OCR capabilities.
  - **MCP (Model Context Protocol):** Integrates external tools using standard protocols.
  - **RAG:** Supports PDF, DOCX, TXT, MD parsing and stores vectors using ChromaDB.