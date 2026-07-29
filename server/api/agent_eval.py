"""Local, privacy-safe Agent capability evaluation API.

The API only wires the versioned evaluator to the existing AgentSessionService.
It does not implement a second agent loop. Live model execution is fail-closed:
dry-run is the default and both a server gate and request opt-in are required.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections import Counter
from functools import partial
from pathlib import Path
from typing import Any

from agent_eval import (
    AgentSessionServiceEvaluationAdapter,
    CatalogLoadError,
    EvaluationInputError,
    EvaluationReport,
    FailureAttribution,
    RealModelEvaluationRunner,
    RealModelRunOptions,
    ScenarioObservation,
    default_fixture_root,
    load_default_scenario_catalog,
)
from agent_eval.models import LiveExecutionBudget, LiveExecutionResult, StrictModel, UsageSummary
from agent_session.models import AgentPromptRequest, AgentSessionCreate
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field

from api.agent_sessions import (
    get_agent_session_service,
    get_agent_session_user,
)
from core.db_manager import run_sync
from security.jwt_auth import TokenPayload

router = APIRouter(prefix="/agent-eval", tags=["Agent Evaluation"])
_LIVE_RUN_LOCK = asyncio.Lock()
_LIVE_GATE = "ENABLE_REAL_MODEL_EVALUATION"


class AgentEvalRunRequest(RealModelRunOptions):
    """API request with an optional provider hint for the existing Agent runtime."""

    provider: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    )

    def runner_options(self) -> RealModelRunOptions:
        return RealModelRunOptions.model_validate(self.model_dump(exclude={"provider"}))


class AgentEvalCatalogSummary(StrictModel):
    id: str
    checksum: str
    scenario_count: int
    by_mode: dict[str, int]


class AgentEvalLiveModelSummary(StrictModel):
    enabled: bool
    default_dry_run: bool = True
    requires_explicit_opt_in: bool = True


class AgentEvalOverview(StrictModel):
    schema_version: int = 1
    catalog: AgentEvalCatalogSummary
    live_model: AgentEvalLiveModelSummary
    latest_report: dict[str, Any] | None = None


def _reports_root() -> Path:
    configured = os.environ.get("OUTPUTS_DIR", "").strip()
    root = Path(configured) if configured else Path(__file__).resolve().parents[2] / "outputs"
    return root.resolve() / "agent-eval" / "reports"


def _latest_report_path() -> Path:
    return _reports_root() / "latest.json"


def _load_latest_report() -> EvaluationReport | None:
    path = _latest_report_path()
    if not path.is_file():
        return None
    try:
        return EvaluationReport.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        # A corrupt local report must not prevent the workbench from starting.
        return None


def _report_summary(report: EvaluationReport | None) -> dict[str, Any] | None:
    if report is None:
        return None
    return {
        "report_id": report.report_id,
        "runner": report.runner.model_dump(mode="json"),
        "summary": report.summary.model_dump(mode="json"),
    }


def _persist_report(report: EvaluationReport) -> None:
    root = _reports_root()
    root.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        report.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    for destination in (root / f"{report.report_id}.json", _latest_report_path()):
        temporary = destination.with_suffix(f"{destination.suffix}.tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)


def _live_enabled() -> bool:
    return os.environ.get(_LIVE_GATE, "").strip().lower() == "true"


async def _drive_agent_session(
    service: Any,
    scenario: Any,
    fixture_path: Path,
    model_id: str,
    budget: LiveExecutionBudget,
    *,
    provider: str | None,
    user_id: str,
) -> LiveExecutionResult:
    """Execute one isolated fixture through the existing AgentSessionService."""

    task_mode = {"coding": "build", "training": "train", "hybrid": "hybrid"}[
        scenario.mode.value
    ]
    session = await run_sync(
        service.create_session,
        AgentSessionCreate(
            agent_id="build",
            title=f"Agent Eval · {scenario.id}",
            project_path=str(fixture_path),
            task_mode=task_mode,
            provider=provider,
            model=model_id,
            autonomy_mode="safe_auto",
        ),
        user_id,
    )
    session_id = str(session.id)
    try:
        result = await service.prompt(
            session_id,
            AgentPromptRequest(
                content=scenario.task,
                provider=provider,
                model=model_id,
            ),
        )
    except asyncio.CancelledError:
        await run_sync(service.interrupt_session, session_id, "agent evaluation timeout")
        raise

    status = str(result.status)
    tool_calls = sum(part.type == "tool_call" for part in result.parts)
    usage = UsageSummary(tool_calls=tool_calls)
    if status == "completed":
        observation = ScenarioObservation(scenario_id=scenario.id)
    else:
        attribution = (
            FailureAttribution.PLATFORM
            if status in {"waiting_permission", "waiting_approval"}
            else FailureAttribution.ENVIRONMENT
            if status == "interrupted"
            else FailureAttribution.AMBIGUOUS
        )
        observation = ScenarioObservation(
            scenario_id=scenario.id,
            blocked=True,
            failure_attribution=attribution,
            error_summary=f"agent session ended with status: {status}",
        )
    return LiveExecutionResult(observation=observation, usage=usage)


@router.get("/overview", response_model=AgentEvalOverview)
async def get_agent_eval_overview(
    _current_user: TokenPayload = Depends(get_agent_session_user),
) -> AgentEvalOverview:
    try:
        catalog = await run_sync(load_default_scenario_catalog)
        latest = await run_sync(_load_latest_report)
    except CatalogLoadError as exc:
        raise HTTPException(status_code=503, detail="Agent evaluation baseline is unavailable") from exc
    mode_counts = Counter(scenario.mode.value for scenario in catalog.scenarios)
    return AgentEvalOverview(
        catalog=AgentEvalCatalogSummary(
            id=catalog.catalog_id,
            checksum=str(catalog.catalog_checksum),
            scenario_count=len(catalog.scenarios),
            by_mode={mode: mode_counts.get(mode, 0) for mode in ("coding", "training", "hybrid")},
        ),
        live_model=AgentEvalLiveModelSummary(enabled=_live_enabled()),
        latest_report=_report_summary(latest),
    )


@router.post("/real-model/run")
async def run_real_model_evaluation(
    request: AgentEvalRunRequest,
    current_user: TokenPayload = Depends(get_agent_session_user),
) -> dict[str, Any]:
    try:
        catalog = await run_sync(load_default_scenario_catalog)
    except CatalogLoadError as exc:
        raise HTTPException(status_code=503, detail="Agent evaluation baseline is unavailable") from exc

    options = request.runner_options()
    planner = RealModelEvaluationRunner(default_fixture_root())
    try:
        plan = planner.plan(catalog, options)
    except EvaluationInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if options.dry_run:
        return plan.model_dump(mode="json")
    if not options.explicit_opt_in:
        raise HTTPException(status_code=403, detail="Live evaluation requires explicit_opt_in=true")
    if not plan.server_enabled:
        raise HTTPException(status_code=403, detail=f"Live evaluation requires {_LIVE_GATE}=true")
    if _LIVE_RUN_LOCK.locked():
        raise HTTPException(status_code=409, detail="Another live Agent evaluation is already running")

    async with _LIVE_RUN_LOCK:
        service = get_agent_session_service()
        driver = partial(
            _drive_agent_session,
            provider=request.provider,
            user_id=current_user.user_id,
        )
        runner = RealModelEvaluationRunner(
            default_fixture_root(),
            AgentSessionServiceEvaluationAdapter(service, driver),
        )
        try:
            result = await runner.run(catalog, options)
        except EvaluationInputError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not isinstance(result, EvaluationReport):
            return result.model_dump(mode="json")
        await run_sync(_persist_report, result)
        return result.model_dump(mode="json")


__all__ = ["router"]
