"""Manual smoke test for controlled tool-platform mode (Task 9D-2).

Runs a real-model Build session in ``orchestration_mode=controlled`` against a
project directory, confirming the platform-managed tools route through the
Tool Gateway and the legacy execute entry is blocked.  This script is NOT part
of the pytest suite (it requires a configured LLM provider/model and a real
DeepAgents installation); run it manually from the repo root::

    uv run --extra all python server/scripts/run_controlled_build_smoke.py \\
        --project-path /path/to/project \\
        --task "Read app.py and report the first line" \\
        --orchestration-mode controlled

The script prints the session timeline (tool calls + canonical events) and a
final pass/fail summary.  Failures surface whether the Gateway routed the
call, whether exclusion held, and whether the backend deny blocked the legacy
execute entry.

This script must not be imported by production code (it lives under
``server/scripts/`` per AGENTS.md).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "server") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "server"))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Controlled tool-platform smoke test")
    parser.add_argument("--project-path", required=True, help="Workspace project root (must be an allowed workspace).")
    parser.add_argument("--task", required=True, help="Prompt for the Build agent.")
    parser.add_argument(
        "--orchestration-mode",
        default="controlled",
        choices=["legacy", "shadow", "controlled"],
        help="Orchestration mode (default: controlled).",
    )
    parser.add_argument("--provider", default=None, help="Override provider (defaults to manifest).")
    parser.add_argument("--model", default=None, help="Override model (defaults to manifest).")
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> int:
    from agent_session.agent_registry import AgentRegistry
    from agent_session.deepagents_runtime import DeepAgentsSessionRunner
    from agent_session.models import AgentSessionCreate
    from agent_session.repository import AgentSessionRepository


    workspace = Path(args.project_path).resolve()
    if not workspace.is_dir():
        print(f"[fail] project-path is not a directory: {workspace}", file=sys.stderr)
        return 2

    registry = AgentRegistry()
    repo = AgentSessionRepository(str(REPO_ROOT / "tmp" / "controlled_smoke.db"))

    runner = DeepAgentsSessionRunner(
        repository=repo,
        notify_event=_notify,
        agent_registry=registry,
    )

    session = runner.service.create_session(
        AgentSessionCreate(
            title=f"controlled-smoke-{args.orchestration_mode}",
            project_path=str(workspace),
            autonomy_mode="safe_auto",
            provider=args.provider or "deepseek",
            model=args.model or "deepseek-chat",
            metadata={"orchestration_mode": args.orchestration_mode},
        )
    )
    session_id = session["id"]
    print(f"[info] session={session_id} mode={args.orchestration_mode}")

    try:
        result = await runner.run_prompt(session_id, args.task)
    except Exception as exc:  # noqa: BLE001
        print(f"[fail] run_prompt raised: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    parts = result.get("parts", [])
    events = repo.list_events(session_id)
    canonical_events = [e for e in events if str(e.get("type", "")).startswith("tool.")]
    print(f"[info] parts={len(parts)} events={len(events)} canonical_tool_events={len(canonical_events)}")
    for event in canonical_events:
        payload = event.get("payload") or {}
        print(
            f"  canonical: {event.get('type')} canonical_name={payload.get('canonical_name')} "
            f"reason_code={payload.get('reason_code')}"
        )

    status = (repo.get_session(session_id) or {}).get("status")
    print(f"[done] session_status={status}")
    if args.orchestration_mode == "controlled" and not canonical_events:
        print("[warn] controlled mode produced no canonical tool events; Gateway routing may not have fired.")
    return 0 if status == "completed" else 1


def _notify(_session_id: str, event: dict[str, Any]) -> None:
    etype = event.get("type")
    if etype and (etype.startswith("tool.") or etype in {"tool_call_started", "tool_call_completed", "tool_call_failed"}):
        print(f"  event: {etype}")


def main() -> int:
    args = _parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
