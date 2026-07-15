"""Versioned, privacy-safe evaluation contracts for the Agent workspace.

The package deliberately does not import ``agent_session``.  Real executions
are supplied by an adapter so this module never becomes a second Agent loop.
"""

from .loader import (
    CatalogLoadError,
    default_catalog_path,
    default_fixture_root,
    load_default_scenario_catalog,
    load_scenario_catalog,
    resolve_fixture_directory,
)
from .models import (
    CriterionObservation,
    CriterionState,
    EvaluationReport,
    FailureAttribution,
    LiveExecutionBudget,
    LiveExecutionResult,
    RealModelRunOptions,
    RealModelRunPlan,
    RunOutcome,
    ScenarioCatalog,
    ScenarioMode,
    ScenarioObservation,
)
from .real_model import (
    RealModelEvaluationRunner,
    RealModelExecutor,
    RealModelExecutorRequired,
    RealModelOptInRequired,
    RealModelServerDisabled,
)
from .agent_session_adapter import AgentSessionServiceEvaluationAdapter
from .runner import DeterministicEvaluationRunner, EvaluationInputError

__all__ = [
    "CatalogLoadError",
    "AgentSessionServiceEvaluationAdapter",
    "CriterionObservation",
    "CriterionState",
    "DeterministicEvaluationRunner",
    "EvaluationInputError",
    "EvaluationReport",
    "FailureAttribution",
    "LiveExecutionBudget",
    "LiveExecutionResult",
    "RealModelEvaluationRunner",
    "RealModelExecutor",
    "RealModelExecutorRequired",
    "RealModelOptInRequired",
    "RealModelServerDisabled",
    "RealModelRunOptions",
    "RealModelRunPlan",
    "RunOutcome",
    "ScenarioCatalog",
    "ScenarioMode",
    "ScenarioObservation",
    "default_catalog_path",
    "default_fixture_root",
    "load_default_scenario_catalog",
    "load_scenario_catalog",
    "resolve_fixture_directory",
]
