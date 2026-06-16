from __future__ import annotations

from agent_session.terminal_manager import TerminalSession, terminal_result_payload


def test_terminal_result_payload_summarizes_recent_failure_output():
    session = TerminalSession(
        id="terminal-1",
        part_id="part-1",
        session_id="session-1",
        command=["pytest", "-q"],
        cwd=".",
        interactive=False,
        exit_code=1,
        stdout="\n".join(f"line-{index}" for index in range(25)),
    )

    payload = terminal_result_payload(session)

    assert payload["failure_summary"].startswith("line-5")
    assert "line-0" not in payload["failure_summary"]
    assert payload["failure_summary"].endswith("line-24")
