from core.agent_run_state import agent_session_state_snapshot


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
