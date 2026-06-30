# Backend application profiles

The backend is a modular monolith with three ASGI assembly profiles. The
default deployment remains the backward-compatible combined application.

| Profile | Entrypoint | Owns |
| --- | --- | --- |
| Combined | `server.main:app` or `server.apps.combined:app` | Every existing API and lifecycle component |
| Agent | `server.apps.agent:app` | Agent sessions, Chat, Knowledge, Memory, Workspace, tools, and experimental Agent capabilities |
| Finetune | `server.apps.finetune:app` | Device, models, datasets, training, evaluation, deployment, and local inference |

Router ownership is defined in `server/apps/routers.py`. Imports are lazy, so
loading one profile does not import the other profile's API modules. Shared
middleware and exception behavior live in `server/apps/factory.py`, while
startup and shutdown ownership lives in `server/apps/lifespan.py`.

## Development commands

```bash
# Default application used by the frontend and existing scripts
uv run python -m uvicorn server.main:app --host 127.0.0.1 --port 8010 --reload

# Boundary-specific applications
uv run python -m uvicorn server.apps.agent:app --host 127.0.0.1 --port 8011
uv run python -m uvicorn server.apps.finetune:app --host 127.0.0.1 --port 8012
```

The profile-specific entrypoints establish code and lifecycle boundaries. They
do not yet introduce a reverse proxy, separate databases, remote inference
transport, or a training worker. Until those later phases are implemented, the
frontend and production scripts should continue using the combined entrypoint.

## Compatibility contract

- Existing API paths and the single frontend base URL are unchanged.
- `server.main:app` remains the canonical default entrypoint.
- Workspace path mapping and files under `data/` are not migrated.
- The combined application owns the automatic backup loop.
- `api.__init__` retains its legacy exports through lazy attribute loading.
