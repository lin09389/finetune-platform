"""P1 regression tests: cover the fixes from PR5/PR6/PR10/PR11/PR12/PR13.

- PR5:  TrainingQueue._load_state 恢复 running 快照(stale → CANCELLED/FAILED)
- PR6:  InProcessTrainingGateway.get_progress(task_id=X) task_id 校验
- PR10: Settings watchdog/cleanup 字段 + pipeline 从 settings 读取
- PR11: _training_recover_loop 在有活 Worker 时不调 recover_expired
- PR12: pipeline cleanup_dangled 标记
- PR13: TrainingProgress.copy() 对 phase_durations 做独立拷贝
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from core.config import Settings
from core.training_state import TrainingProgress

# ---------------------------------------------------------------------------
# PR5: TrainingQueue running snapshot recovery
# ---------------------------------------------------------------------------


def test_recover_from_state_marks_stale_running_tasks_as_cancelled(tmp_path):
    """PR5: 进程重启后,_load_state 把 running 快照中的任务标记为 CANCELLED(< 24h)
    或 FAILED(> 24h)。
    """
    from core.training_queue import TaskStatus, TrainingQueue

    state_file = tmp_path / "queue_state.json"
    now = datetime.now()

    # recent_task: 1 小时前 started → CANCELLED
    # stale_task: 25 小时前 started → FAILED
    state = {
        "history": {},
        "running": {
            "recent-task": {
                "priority": 2,
                "created_at": now.timestamp(),
                "started_at": (now - timedelta(hours=1)).isoformat(),
                "status": "running",
            },
            "stale-task": {
                "priority": 2,
                "created_at": (now - timedelta(hours=25)).timestamp(),
                "started_at": (now - timedelta(hours=25)).isoformat(),
                "status": "running",
            },
        },
    }
    state_file.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    queue = TrainingQueue(state_file=state_file)

    # PR5 契约:running 快照中的任务被搬入 _history,标记为 CANCELLED 或 FAILED
    assert "recent-task" in queue._history
    assert "stale-task" in queue._history

    recent = queue._history["recent-task"]
    stale = queue._history["stale-task"]

    assert recent.status == TaskStatus.CANCELLED, (
        f"recent running task should be CANCELLED, got {recent.status}"
    )
    assert "process restart" in (recent.error or ""), (
        f"recent task error should mention process restart, got: {recent.error}"
    )

    assert stale.status == TaskStatus.FAILED, (
        f"stale running task (>24h) should be FAILED, got {stale.status}"
    )
    assert "stale" in (stale.error or "").lower() or "24" in (stale.error or ""), (
        f"stale task error should mention stale/24h, got: {stale.error}"
    )


# ---------------------------------------------------------------------------
# PR6: InProcessTrainingGateway.get_progress task_id validation
# ---------------------------------------------------------------------------


def test_get_progress_returns_idle_for_non_active_task_id(monkeypatch):
    """PR6: get_progress(task_id=X) 当 X ≠ current_record.id → 走 idle 分支。

    用 mock 捕获 TrainingProgressResponse 构造调用,断言传入 status="idle"
    且 message="Task not active",且 state.get_progress() 未被调用(短路)。
    """
    from core.training_gateway import InProcessTrainingGateway

    gateway = InProcessTrainingGateway()

    # 让 state.get_current_record() 返回一个 id="active-task" 的 record
    active_record = SimpleNamespace(id="active-task")
    monkeypatch.setattr(
        gateway.context.state, "get_current_record", lambda: active_record
    )
    # state.get_progress 不应被调用(短路);若被调用则测试失败
    state_get_progress_called = {"v": False}

    def spy_get_progress():
        state_get_progress_called["v"] = True
        return TrainingProgress()

    monkeypatch.setattr(gateway.context.state, "get_progress", spy_get_progress)

    # Mock TrainingProgressResponse 以捕获构造参数(生产代码中它有必填字段,
    # 此处不验证 schema,只验证 PR6 短路分支被进入)
    captured = {}

    class _FakePR:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def model_dump(self):
            return dict(captured)

    import training_engine.schemas as schemas_mod
    monkeypatch.setattr(schemas_mod, "TrainingProgressResponse", _FakePR)

    result = gateway.get_progress(task_id="other-task")

    # PR6 契约:task_id 不匹配时,构造 idle response
    assert captured.get("status") == "idle", (
        f"expected idle status in constructed response, got: {captured.get('status')}"
    )
    assert captured.get("message") == "Task not active", (
        f"expected 'Task not active' message, got: {captured.get('message')}"
    )
    # 短路:state.get_progress() 不应被调用
    assert state_get_progress_called["v"] is False, (
        "state.get_progress() must NOT be called when task_id mismatches current_record"
    )
    # 返回值应来自 idle 构造
    assert result["status"] == "idle"


# ---------------------------------------------------------------------------
# PR10a: Settings watchdog/cleanup Field bounds
# ---------------------------------------------------------------------------


def test_settings_watchdog_and_cleanup_fields_validate_bounds():
    """PR10a: 3 个新 Field 存在且 ge/le 边界校验生效。"""
    # training_watchdog_stall_seconds: ge=60, le=3600
    with pytest.raises(ValidationError):
        Settings(training_watchdog_stall_seconds=30)
    with pytest.raises(ValidationError):
        Settings(training_watchdog_stall_seconds=4000)
    Settings(training_watchdog_stall_seconds=300)  # 通过

    # training_watchdog_timeout_seconds: ge=120, le=7200
    with pytest.raises(ValidationError):
        Settings(training_watchdog_timeout_seconds=60)
    with pytest.raises(ValidationError):
        Settings(training_watchdog_timeout_seconds=8000)
    Settings(training_watchdog_timeout_seconds=600)  # 通过

    # training_cleanup_timeout_seconds: ge=10, le=600
    with pytest.raises(ValidationError):
        Settings(training_cleanup_timeout_seconds=5)
    with pytest.raises(ValidationError):
        Settings(training_cleanup_timeout_seconds=700)
    Settings(training_cleanup_timeout_seconds=60)  # 通过


# ---------------------------------------------------------------------------
# PR10b: pipeline watchdog reads settings, not hardcoded
# ---------------------------------------------------------------------------


def test_pipeline_watchdog_reads_settings_not_hardcoded():
    """PR10b: pipeline.py 中 watchdog 阈值从 settings 读取,不再硬编码 300/600。"""
    pipeline_path = Path(__file__).resolve().parents[1] / "training_engine" / "pipeline.py"
    source = pipeline_path.read_text(encoding="utf-8")

    # 必须含 settings.training_watchdog_stall_seconds 与 ..._timeout_seconds
    assert "training_watchdog_stall_seconds" in source, (
        "pipeline.py must reference settings.training_watchdog_stall_seconds"
    )
    assert "training_watchdog_timeout_seconds" in source, (
        "pipeline.py must reference settings.training_watchdog_timeout_seconds"
    )

    # 不应回退为硬编码字面量(允许默认值在 config.py 中,但 pipeline.py 不该硬编码)
    # 排除注释行(# ... = 300)和文档字符串中的历史描述
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        # 不允许 STALL_TIMEOUT_SECONDS = 300 或 WATCHDOG_TIMEOUT_SECONDS = 600 这样的硬编码
        assert "STALL_TIMEOUT_SECONDS = 300" not in stripped, (
            f"pipeline.py must not hardcode STALL_TIMEOUT_SECONDS = 300: {stripped}"
        )
        assert "WATCHDOG_TIMEOUT_SECONDS = 600" not in stripped, (
            f"pipeline.py must not hardcode WATCHDOG_TIMEOUT_SECONDS = 600: {stripped}"
        )


# ---------------------------------------------------------------------------
# PR11: _training_recover_loop skips recover_expired when workers alive
# ---------------------------------------------------------------------------


def test_training_recover_loop_skips_when_workers_alive(monkeypatch):
    """PR11: 有活 Worker 时,_training_recover_loop 不调 recover_expired。"""
    from apps import lifespan as lifespan_mod

    fake_repo = MagicMock()
    fake_repo.worker_status.return_value = [
        {"worker_id": "w1", "status": "online"},
    ]
    fake_repo.recover_expired = MagicMock(return_value={"requeued": 0, "interrupted": 0, "cancelled": 0})

    monkeypatch.setattr(
        "training_worker.repository.get_training_job_repository",
        lambda: fake_repo,
    )

    # 让 asyncio.sleep 第一次成功(让循环体执行),第二次抛 CancelledError 退出
    sleep_count = {"n": 0}

    async def fake_sleep(seconds):
        sleep_count["n"] += 1
        if sleep_count["n"] == 1:
            return  # 第一次 sleep 完成 → 循环体执行(worker_status 等被调用)
        # 第二次 sleep 时取消,使 while True 循环退出
        raise asyncio.CancelledError()

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(lifespan_mod._training_recover_loop())

    # PR11 契约:有活 Worker 时,不应调用 recover_expired
    assert fake_repo.recover_expired.call_count == 0, (
        f"recover_expired should NOT be called when workers alive; "
        f"got {fake_repo.recover_expired.call_count} calls"
    )
    # worker_status 应该被调用一次(用于判断是否有活 Worker)
    assert fake_repo.worker_status.call_count == 1, (
        f"worker_status should be called once; "
        f"got {fake_repo.worker_status.call_count} calls"
    )


# ---------------------------------------------------------------------------
# PR12: pipeline cleanup_dangled flag
# ---------------------------------------------------------------------------


def test_pipeline_cleanup_dangled_flag_logic_exists():
    """PR12: pipeline.py 含 cleanup_dangled 标记逻辑(join 超时 → True)。"""
    pipeline_path = Path(__file__).resolve().parents[1] / "training_engine" / "pipeline.py"
    source = pipeline_path.read_text(encoding="utf-8")

    # 必须含 self._cleanup_dangled = True 赋值
    assert "self._cleanup_dangled = True" in source, (
        "pipeline.py must set self._cleanup_dangled = True on join timeout"
    )
    # 必须含 cleanup_thread.is_alive() 判断
    assert "cleanup_thread.is_alive()" in source, (
        "pipeline.py must check cleanup_thread.is_alive() to detect timeout"
    )
    # 必须含 cleanup_dangled 属性(property)
    assert "def cleanup_dangled" in source, (
        "pipeline.py must expose cleanup_dangled property"
    )
    # 必须从 settings 读取 cleanup_timeout(配置化,非硬编码)
    assert "training_cleanup_timeout_seconds" in source, (
        "pipeline.py must read training_cleanup_timeout_seconds from settings"
    )


# ---------------------------------------------------------------------------
# PR13: TrainingProgress.copy() phase_durations deep copy
# ---------------------------------------------------------------------------


def test_training_progress_copy_independently_copies_phase_durations():
    """PR13: TrainingProgress.copy() 返回的 phase_durations 是独立 dict。"""
    original = TrainingProgress(phase_durations={"loading": 5.0, "training": 100.0})
    copied = original.copy()

    # 修改副本不影响原对象
    copied.phase_durations["loading"] = 999.0
    copied.phase_durations["new_phase"] = 1.0

    assert original.phase_durations["loading"] == 5.0, (
        "original.phase_durations['loading'] must be unchanged after copy mutation"
    )
    assert "new_phase" not in original.phase_durations, (
        "original.phase_durations must not see new key added to copy"
    )
    assert copied.phase_durations["loading"] == 999.0
    assert copied.phase_durations["new_phase"] == 1.0

    # 反向验证:修改原对象不影响副本
    original.phase_durations["training"] = 0.0
    assert copied.phase_durations["training"] == 100.0, (
        "copied.phase_durations['training'] must be unchanged after original mutation"
    )
