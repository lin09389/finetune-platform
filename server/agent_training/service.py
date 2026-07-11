"""Approval-gated application service for future agent training tools."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from agent_training.errors import AgentTrainingError
from agent_training.models import (
    ApprovedTrainingAction,
    TrainingProposal,
    TrainingProposalRequest,
    TrainingRunSummary,
    TrainingSubmission,
)
from agent_training.store import TrainingProposalStore
from core.config import Settings, get_settings
from core.training_context import get_training_context
from core.training_state import TrainingState
from services.training.orchestrator import resolve_dataset_file, start_training_task
from services.training.records import find_training_record
from services.training.validator import (
    TrainingValidator,
    estimate_preflight_required_vram,
    validate_release_supported_features,
)


class AgentTrainingService:
    """Diagnose training requests and submit only explicitly approved proposals.

    Proposal state is persisted when the application settings provide a base
    directory, so an approval cannot silently disappear or be double-submitted
    when requests are served by different processes.
    """

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        state: TrainingState | None = None,
        proposal_store: TrainingProposalStore | None = None,
        proposal_id_factory: Callable[[], str] | None = None,
    ):
        self._settings = settings or get_settings()
        self._state = state
        self._proposal_store = proposal_store or TrainingProposalStore(db_path=self._proposal_store_path())
        self._proposal_id_factory = proposal_id_factory or (lambda: str(uuid.uuid4()))

    def _proposal_store_path(self) -> Path | None:
        base_dir = getattr(self._settings, "base_dir", None)
        if not base_dir:
            return None
        return Path(base_dir).resolve() / "data" / "agent_training_proposals.sqlite3"

    async def create_proposal(
        self,
        request: TrainingProposalRequest,
        *,
        owner_id: str | None = None,
        session_id: str | None = None,
    ) -> TrainingProposal:
        """Return a diagnostic proposal without creating files or submitting work."""
        config = request.config
        blockers: list[str] = []
        warnings: list[str] = []

        model_path = self._resolve_catalog_directory(self._settings.models_dir_resolved, config.model_id)
        if not model_path.exists():
            blockers.append(f"Model not found: {config.model_id}")

        if self._resolve_dataset_file(config.dataset_id) is None:
            blockers.append(f"Dataset file not found: {config.dataset_id}")

        validation = await TrainingValidator.validate_config(config, self._settings)
        blockers.extend(validation.errors)
        warnings.extend(validation.warnings)

        required_vram_gb: float | None = None
        try:
            required_vram_gb = estimate_preflight_required_vram(config)
        except Exception as exc:
            warnings.append(f"VRAM estimate unavailable: {exc}")

        status = "blocked" if blockers else "warning" if warnings else "ready"
        proposal = TrainingProposal(
            proposal_id=self._proposal_id_factory(),
            config=config,
            owner_id=self._normalize_scope_value(owner_id),
            session_id=self._normalize_scope_value(session_id),
            created_at=datetime.now(timezone.utc),
            use_queue=request.use_queue,
            priority=request.priority,
            status=status,
            blockers=blockers,
            warnings=warnings,
            suggestions=self._suggest(config, required_vram_gb),
            required_vram_gb=required_vram_gb,
        )
        return self._proposal_store.add(proposal)

    async def propose_training(
        self,
        request: TrainingProposalRequest,
        *,
        owner_id: str | None = None,
        session_id: str | None = None,
    ) -> TrainingProposal:
        """Tool-friendly alias for :meth:`create_proposal`."""
        return await self.create_proposal(request, owner_id=owner_id, session_id=session_id)

    def submit_approved_training(
        self,
        action: ApprovedTrainingAction,
        *,
        owner_id: str | None = None,
        session_id: str | None = None,
    ) -> TrainingSubmission:
        """Submit an approved, ready proposal through the established orchestrator."""
        if not action.approved:
            raise AgentTrainingError(
                "approval_required",
                "Training proposals require approved=True before submission.",
                details={"proposal_id": action.proposal_id},
            )

        proposal = self._proposal_store.get(action.proposal_id)
        if proposal is None:
            raise AgentTrainingError(
                "proposal_not_found",
                "Training proposal is unknown or expired; request a new proposal.",
                details={"proposal_id": action.proposal_id},
            )
        self._require_matching_scope(proposal, owner_id=owner_id, session_id=session_id)
        if proposal.status == "blocked":
            raise AgentTrainingError(
                "proposal_blocked",
                "Blocked training proposals cannot be submitted.",
                details={"proposal_id": proposal.proposal_id, "blockers": proposal.blockers},
            )
        if not self._proposal_store.claim_submission(action.proposal_id):
            raise AgentTrainingError(
                "proposal_already_submitted",
                "Training proposal has already been submitted.",
                details={"proposal_id": action.proposal_id},
            )

        try:
            model_path, dataset_file = self._resolve_submission_paths(proposal)
            self._validate_submission_config(proposal.config)
            record = start_training_task(
                config=proposal.config.model_copy(deep=True),
                state=self._submission_state(),
                settings=self._settings,
                model_path=model_path,
                dataset_file=dataset_file,
                use_queue=proposal.use_queue,
                priority=proposal.priority,
            )
        except Exception:
            self._proposal_store.release_submission(action.proposal_id)
            raise

        return TrainingSubmission(
            proposal_id=proposal.proposal_id,
            task_id=record.id,
            status=record.status,
        )

    def submit_training(
        self,
        action: ApprovedTrainingAction,
        *,
        owner_id: str | None = None,
        session_id: str | None = None,
    ) -> TrainingSubmission:
        """Tool-friendly alias for :meth:`submit_approved_training`."""
        return self.submit_approved_training(action, owner_id=owner_id, session_id=session_id)

    def get_run_summary(self, task_id: str) -> TrainingRunSummary:
        """Return a read-only projection of an authoritative training record."""
        record = find_training_record(task_id)
        if record is None:
            raise AgentTrainingError(
                "training_run_not_found",
                "Training run was not found.",
                details={"task_id": task_id},
            )
        return TrainingRunSummary(
            task_id=record.id,
            status=record.status,
            model_id=record.base_model_id or record.model_name,
            dataset_id=record.dataset_id or record.dataset_name,
            method=record.method,
            task_goal=record.task_goal,
            started_at=record.start_time,
            completed_at=record.end_time,
            output_path=record.output_path,
            adapter_path=record.adapter_path,
            checkpoint_path=record.checkpoint_path,
            final_loss=record.final_loss,
            elapsed_time=record.elapsed_time,
        )

    def get_training_run_summary(self, task_id: str) -> TrainingRunSummary:
        """Tool-friendly alias for :meth:`get_run_summary`."""
        return self.get_run_summary(task_id)

    def _resolve_submission_paths(self, proposal: TrainingProposal):
        """Resolve paths again at execution time to reject stale proposals safely."""
        model_path = self._resolve_catalog_directory(self._settings.models_dir_resolved, proposal.config.model_id)
        if not model_path.exists():
            raise AgentTrainingError(
                "proposal_stale",
                "Model is no longer available; request a new training proposal.",
                details={"proposal_id": proposal.proposal_id, "model_id": proposal.config.model_id},
            )
        dataset_file = self._resolve_dataset_file(proposal.config.dataset_id)
        if dataset_file is None:
            raise AgentTrainingError(
                "proposal_stale",
                "Dataset is no longer available; request a new training proposal.",
                details={"proposal_id": proposal.proposal_id, "dataset_id": proposal.config.dataset_id},
            )
        return model_path, dataset_file

    def _resolve_dataset_file(self, dataset_id: str) -> Path | None:
        """Resolve a dataset identifier without permitting traversal out of the catalog."""
        self._resolve_catalog_directory(self._settings.datasets_dir_resolved, dataset_id)
        dataset_file = resolve_dataset_file(self._settings, dataset_id)
        if dataset_file is None:
            return None
        try:
            resolved_file = dataset_file.resolve(strict=True)
            datasets_root = self._settings.datasets_dir_resolved.resolve(strict=True)
            if not resolved_file.is_file() or not resolved_file.is_relative_to(datasets_root):
                return None
            return resolved_file
        except (OSError, ValueError):
            return None

    @staticmethod
    def _resolve_catalog_directory(root: Path, identifier: str) -> Path:
        """Resolve a single catalog ID and reject absolute, traversal, and nested paths."""
        raw = str(identifier or "").strip()
        candidate = Path(raw)
        if not raw or candidate.is_absolute() or len(candidate.parts) != 1 or raw in {".", ".."}:
            raise AgentTrainingError(
                "invalid_catalog_id",
                "Model and dataset identifiers must be a single catalog directory name.",
                details={"identifier": raw},
            )
        try:
            resolved_root = root.resolve(strict=False)
            resolved = (resolved_root / candidate).resolve(strict=False)
            if not resolved.is_relative_to(resolved_root):
                raise ValueError("outside catalog root")
            return resolved
        except (OSError, ValueError) as exc:
            raise AgentTrainingError(
                "invalid_catalog_id",
                "Model or dataset identifier is outside the configured catalog.",
                details={"identifier": raw},
            ) from exc

    def _validate_submission_config(self, config) -> None:
        """Repeat the complete preflight at approval time before task creation.

        DeepAgents tools run on the asyncio event loop.  ``asyncio.run`` is
        illegal there, so when a loop is already running the preflight is
        executed in a short-lived worker thread that owns its own loop.
        """
        import asyncio
        from concurrent.futures import ThreadPoolExecutor

        try:
            validate_release_supported_features(config)
        except Exception as exc:
            raise AgentTrainingError(
                "proposal_stale",
                "Training proposal no longer passes release validation; request a new proposal.",
                details={"error": str(exc)},
            ) from exc

        def _run_preflight():
            return asyncio.run(TrainingValidator.validate_config(config, self._settings))

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            validation = _run_preflight()
        else:
            with ThreadPoolExecutor(max_workers=1) as executor:
                validation = executor.submit(_run_preflight).result()
        if validation.errors:
            raise AgentTrainingError(
                "proposal_stale",
                "Training proposal no longer passes preflight; request a new proposal.",
                details={"errors": validation.errors},
            )

    @staticmethod
    def _normalize_scope_value(value: str | None) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

    def _require_matching_scope(
        self,
        proposal: TrainingProposal,
        *,
        owner_id: str | None,
        session_id: str | None,
    ) -> None:
        expected = (proposal.owner_id, proposal.session_id)
        actual = (self._normalize_scope_value(owner_id), self._normalize_scope_value(session_id))
        if expected != actual:
            raise AgentTrainingError(
                "proposal_scope_mismatch",
                "Training proposal belongs to a different user or Agent session.",
                details={"proposal_id": proposal.proposal_id},
            )

    def _submission_state(self) -> TrainingState | None:
        if self._settings.training_execution_mode == "worker":
            return None
        return self._state or get_training_context().state

    @staticmethod
    def _suggest(config, required_vram_gb: float | None) -> list[str]:
        if required_vram_gb and config.method == "lora" and config.quantization == 0:
            return ["Consider QLoRA with 4-bit quantization to reduce VRAM requirements."]
        return []


__all__ = ["AgentTrainingService"]
