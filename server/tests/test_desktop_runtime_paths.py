from pathlib import Path

from apps.factory import resolve_log_dir


def test_desktop_log_dir_can_live_outside_immutable_app_resources(monkeypatch, tmp_path: Path):
    desktop_logs = tmp_path / "user-data" / "logs"
    monkeypatch.setenv("FINETUNE_LOG_DIR", str(desktop_logs))

    assert resolve_log_dir() == desktop_logs.resolve()


def test_desktop_log_dir_expands_user_home(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("FINETUNE_LOG_DIR", "~/finetune-logs")

    assert resolve_log_dir() == (tmp_path / "finetune-logs").resolve()
