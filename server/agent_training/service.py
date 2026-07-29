"""Approval-gated application service for future agent training tools."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from services.training.orchestrator import resolve_dataset_file, start_training_task
from services.training.records import find_training_record
from services.training.validator import (
    TrainingValidator,
    estimate_preflight_required_vram,
    validate_release_supported_features,
)
from training_engine.schemas import TrainingConfigInput

from agent_training.errors import AgentTrainingError
from agent_training.models import (
    ApprovedTrainingAction,
    TrainingCancelResult,
    TrainingProposal,
    TrainingProposalRequest,
    TrainingResumeResult,
    TrainingRunSummary,
    TrainingSubmission,
)
from agent_training.store import TrainingProposalStore
from core.config import Settings, get_settings
from core.training_context import get_training_context
from core.training_state import TrainingState


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
            # P1-3: 调用同步版本 — submit_approved_training 本身是同步方法,
            # 在线程池或同步上下文中运行,无需 asyncio.to_thread 包装。
            self._validate_submission_config_sync(proposal.config)
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

    def resume_training(
        self,
        *,
        task_id: str,
        checkpoint_name: str,
        owner_id: str | None = None,
        session_id: str | None = None,
    ) -> TrainingResumeResult:
        """Start a new training job from a validated checkpoint of an existing run.

        ``owner_id`` / ``session_id`` are accepted for API symmetry with submit;
        session ownership must be enforced by the tool layer via training links.
        """
        _ = owner_id, session_id
        source_task_id = str(task_id or "").strip()
        checkpoint = self._sanitize_checkpoint_name(checkpoint_name)
        record = find_training_record(source_task_id)
        if record is None:
            raise AgentTrainingError(
                "training_run_not_found",
                "Training run was not found.",
                details={"task_id": source_task_id},
            )

        output_dir = Path(str(record.output_path or "")).expanduser()
        if not str(record.output_path or "").strip():
            raise AgentTrainingError(
                "checkpoint_not_found",
                "Training run has no output path; cannot locate checkpoints.",
                details={"task_id": source_task_id},
            )
        try:
            output_dir = output_dir.resolve(strict=False)
        except OSError as exc:
            raise AgentTrainingError(
                "checkpoint_not_found",
                "Training output path is invalid.",
                details={"task_id": source_task_id},
            ) from exc
        checkpoint_path = (output_dir / "checkpoints" / checkpoint).resolve(strict=False)
        if not checkpoint_path.is_relative_to(output_dir.resolve(strict=False)):
            raise AgentTrainingError(
                "invalid_checkpoint_name",
                "Checkpoint path escapes the training output directory.",
                details={"checkpoint_name": checkpoint},
            )
        if not checkpoint_path.exists():
            raise AgentTrainingError(
                "checkpoint_not_found",
                "Checkpoint was not found for this training run.",
                details={"task_id": source_task_id, "checkpoint_name": checkpoint},
            )

        from training_engine.checkpoint_manager import validate_checkpoint

        validation = validate_checkpoint(str(checkpoint_path))
        if not validation.get("valid"):
            missing = validation.get("missing") or []
            raise AgentTrainingError(
                "checkpoint_invalid",
                "Checkpoint is incomplete and cannot be used for resumption.",
                details={"missing": missing, "checkpoint_name": checkpoint},
            )
        if not validation.get("has_trainer_state"):
            raise AgentTrainingError(
                "checkpoint_invalid",
                "Checkpoint is missing trainer_state.json and cannot be resumed.",
                details={"checkpoint_name": checkpoint},
            )

        if self._settings.training_execution_mode == "worker":
            from training_worker.repository import get_training_job_repository

            if get_training_job_repository().active_job() is not None:
                raise AgentTrainingError(
                    "training_busy",
                    "Training already in progress; wait for it to finish before resuming.",
                    details={"task_id": source_task_id},
                )
        else:
            state = self._submission_state()
            if state is not None and state.is_training():
                raise AgentTrainingError(
                    "training_busy",
                    "Training already in progress; wait for it to finish before resuming.",
                    details={"task_id": source_task_id},
                )

        config_dict = dict(record.config or {})
        try:
            from services.training.resume_identity import (
                ResumeIdentityError,
                validate_resume_identity,
            )

            identity_warnings = validate_resume_identity(
                original_record=record,
                config_dict=config_dict,
                checkpoint_path=checkpoint_path,
            )
        except ResumeIdentityError as exc:
            raise AgentTrainingError(
                getattr(exc, "code", None) or "checkpoint_identity_mismatch",
                str(exc),
                details={"task_id": source_task_id, "checkpoint_name": checkpoint},
            ) from exc
        config_dict["resume_from_checkpoint"] = str(checkpoint_path)
        if identity_warnings:
            config_dict["resume_identity_warnings"] = identity_warnings
        try:
            config = TrainingConfigInput.model_validate(config_dict)
        except Exception as exc:
            raise AgentTrainingError(
                "proposal_stale",
                "Stored training config is no longer valid for resume; start a new proposal.",
                details={"error": str(exc)},
            ) from exc

        model_path = self._resolve_catalog_directory(self._settings.models_dir_resolved, config.model_id)
        if not model_path.exists():
            raise AgentTrainingError(
                "proposal_stale",
                "Model is no longer available; request a new training proposal.",
                details={"model_id": config.model_id},
            )
        dataset_file = self._resolve_dataset_file(config.dataset_id)
        if dataset_file is None:
            raise AgentTrainingError(
                "proposal_stale",
                "Dataset is no longer available; request a new training proposal.",
                details={"dataset_id": config.dataset_id},
            )

        try:
            started = start_training_task(
                config=config,
                state=self._submission_state(),
                settings=self._settings,
                model_path=model_path,
                dataset_file=dataset_file,
                use_queue=False,
                priority="normal",
                record_id=source_task_id,
                output_path=output_dir,
            )
        except Exception as exc:
            raise AgentTrainingError(
                "resume_failed",
                f"Failed to start resume training: {exc}",
                details={"task_id": source_task_id, "checkpoint_name": checkpoint},
            ) from exc

        return TrainingResumeResult(
            source_task_id=source_task_id,
            checkpoint_name=checkpoint,
            task_id=started.id,
            status=started.status,
        )

    def cancel_training(
        self,
        *,
        task_id: str,
        owner_id: str | None = None,
        session_id: str | None = None,
    ) -> TrainingCancelResult:
        """Request stop/cancel for a training task (session ownership enforced by tools)."""
        _ = owner_id, session_id
        target_id = str(task_id or "").strip()
        if not target_id:
            raise AgentTrainingError("invalid_task_id", "task_id is required.")

        if self._settings.training_execution_mode == "worker":
            from training_worker.repository import get_training_job_repository

            repository = get_training_job_repository()
            job = repository.get_job(target_id)
            if job is None:
                raise AgentTrainingError(
                    "training_run_not_found",
                    "Training run was not found.",
                    details={"task_id": target_id},
                )
            result = repository.request_cancel(target_id)
            if result is None:
                return TrainingCancelResult(
                    task_id=target_id,
                    status=str(job.status or "terminal"),
                    message="Training is already terminal; no cancel was needed.",
                )
            return TrainingCancelResult(
                task_id=target_id,
                status="stopping",
                message=f"Cancellation requested for training task {target_id}.",
            )

        # in_process: only the active run can be stopped; never stop a different job.
        state = self._submission_state()
        if state is None or not state.is_training():
            raise AgentTrainingError(
                "training_not_running",
                "No in-process training is currently running.",
                details={"task_id": target_id},
            )
        current_record = state.get_current_record()
        active_id = str(getattr(current_record, "id", "") or "") if current_record is not None else ""
        if not active_id:
            raise AgentTrainingError(
                "training_not_running",
                "No active training record is bound to the in-process trainer.",
                details={"task_id": target_id},
            )
        if active_id != target_id:
            raise AgentTrainingError(
                "training_run_mismatch",
                "The requested task is not the currently running training job.",
                details={"task_id": target_id, "active_task_id": active_id},
            )
        # Mirror InProcessTrainingGateway.stop: request stop + progress signal.
        if state.should_stop():
            return TrainingCancelResult(
                task_id=target_id,
                status="stopping",
                message="Stop already requested for the active training task.",
            )
        state.request_stop()
        try:
            from training_engine.callbacks import queue_training_progress

            queue_training_progress(
                state,
                status="stopping",
                message="Stop requested, waiting for current step to finish",
            )
        except Exception:
            # Progress fan-out is best-effort; the stop latch is already set.
            pass
        return TrainingCancelResult(
            task_id=target_id,
            status="stopping",
            message=f"Stop requested for training task {target_id}.",
        )

    @staticmethod
    def _sanitize_checkpoint_name(checkpoint_name: str) -> str:
        raw = str(checkpoint_name or "").strip()
        candidate = Path(raw)
        if (
            not raw
            or candidate.is_absolute()
            or len(candidate.parts) != 1
            or raw in {".", ".."}
            or "/" in raw
            or "\\" in raw
        ):
            raise AgentTrainingError(
                "invalid_checkpoint_name",
                "Checkpoint name must be a single directory name under the run's checkpoints folder.",
                details={"checkpoint_name": raw},
            )
        return raw

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

    def _validate_submission_config_sync(self, config) -> None:
        """Synchronous preflight executed at approval time before task creation.

        P1-3: Extracted from the original ``_validate_submission_config`` so that
        synchronous callers (e.g. ``submit_approved_training``) can invoke it
        directly, while async callers go through ``_validate_submission_config``
        which wraps this method with ``asyncio.to_thread``.

        ``asyncio.run`` is safe here because this method runs either in a worker
        thread (when called via ``asyncio.to_thread``) or in a synchronous
        context where no event loop is running (FastAPI sync routes run in the
        threadpool, DeepAgents tool dispatch is async and uses the async wrapper).
        """
        import asyncio

        try:
            validate_release_supported_features(config)
        except Exception as exc:
            raise AgentTrainingError(
                "proposal_stale",
                "Training proposal no longer passes release validation; request a new proposal.",
                details={"error": str(exc)},
            ) from exc

        validation = asyncio.run(TrainingValidator.validate_config(config, self._settings))
        if validation.errors:
            raise AgentTrainingError(
                "proposal_stale",
                "Training proposal no longer passes preflight; request a new proposal.",
                details={"errors": validation.errors},
            )

    async def _validate_submission_config(self, config) -> None:
        """Async wrapper that runs the blocking preflight in a worker thread.

        DeepAgents tools run on the asyncio event loop; calling
        ``_validate_submission_config_sync`` directly would block the loop.
        Use this coroutine from async routes / async tool dispatch.
        """
        import asyncio

        await asyncio.to_thread(self._validate_submission_config_sync, config)

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
        """生成针对当前 config 的优化建议(展示给用户,非强制)。

        P3-2: 扩展启发式覆盖 method=full + 高 VRAM、batch_size 过大、
        未启用 gradient_checkpointing、未启用 flash_attn 等常见可优化点。
        所有建议以中文输出,与 validator.py 警告语言保持一致。
        """
        suggestions: list[str] = []
        vram = required_vram_gb or 0.0

        # 1. 原有启发式:lora + 无量化 → 建议 QLoRA
        if vram and config.method == "lora" and config.quantization == 0:
            suggestions.append("考虑使用 QLoRA(4-bit 量化)以降低 VRAM 占用。")

        # 2. full + 高 VRAM → 建议 LoRA/QLoRA
        if vram and config.method == "full" and vram > 24.0:
            suggestions.append(
                f"全参数训练预估 VRAM {vram:.1f}GB 较高,考虑改用 LoRA 或 QLoRA 以显著降低显存需求。"
            )

        # 3. batch_size 过大 + 高 VRAM → 建议降低 batch_size 或启用梯度累积
        if vram and vram > 16.0 and config.batch_size > 4:
            suggestions.append(
                f"batch_size={config.batch_size} 在预估 VRAM {vram:.1f}GB 下可能 OOM,"
                f"建议降至 1-2 并增大 gradient_accumulation(当前 {config.gradient_accumulation})。"
            )

        # 4. 高 VRAM + 未启用 gradient_checkpointing → 建议启用
        if vram and vram > 16.0 and not config.gradient_checkpointing:
            suggestions.append(
                "启用 gradient_checkpointing 可降低 30-50% 显存,代价是约 20% 训练速度。"
            )

        # 5. 未启用 use_flash_attn → 建议启用(适用于支持的模型)
        if not config.use_flash_attn:
            suggestions.append(
                "启用 use_flash_attn 可降低注意力层显存并加速训练(需 flash-attn 包)。"
            )

        # 6. lora + rank 过高(>=64)→ 建议降 rank
        if config.method in ("lora", "qlora") and config.rank >= 64:
            suggestions.append(
                f"LoRA rank={config.rank} 较高,通常 8-32 已足够;过高会增加可训练参数与显存。"
            )

        # 7. epochs 过高(>10)→ 提醒过拟合风险
        if config.epochs > 10:
            suggestions.append(
                f"epochs={config.epochs} 较高,小数据集易过拟合;建议配合 early_stopping_patience 使用。"
            )

        return suggestions


__all__ = ["AgentTrainingService"]
