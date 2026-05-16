from core.agent_run_state import agent_session_state_snapshot, workflow_state_snapshot


def test_workflow_snapshot_normalizes_blocked_legacy_state():
    snapshot = workflow_state_snapshot(
        {
            "status": "awaiting_approval",
            "current_stage": "plan_approval",
            "metadata": {
                "execution_state": "waiting_approval",
                "active_agent_id": "planner",
                "blocked_state": {"reason": "需要审批"},
            },
        }
    )

    assert snapshot.runtime_kind == "workflow_legacy"
    assert snapshot.status == "blocked"
    assert snapshot.phase == "waiting_approval"
    assert snapshot.active_agent_id == "planner"
    assert snapshot.latest_error == "需要审批"
    assert snapshot.recoverable is True


def test_agent_session_snapshot_normalizes_nested_state():
    snapshot = agent_session_state_snapshot(
        {
            "status": "waiting_permission",
            "agent_id": "build",
            "metadata": {
                "state": {
                    "current_phase": "waiting_permission",
                    "stage": "verify",
                    "node": "run_tests",
                    "latest_error": "需要权限",
                }
            },
        }
    )

    assert snapshot.runtime_kind == "agent_session"
    assert snapshot.status == "blocked"
    assert snapshot.phase == "waiting_permission"
    assert snapshot.current_stage == "verify"
    assert snapshot.current_node == "run_tests"
    assert snapshot.latest_error == "需要权限"
