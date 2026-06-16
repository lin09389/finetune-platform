from __future__ import annotations

import asyncio
import os
import signal
import shutil
import subprocess
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


MAX_CAPTURE_BYTES = 1024 * 1024
TerminalExitCallback = Callable[["TerminalSession"], None]
TerminalOutputCallback = Callable[["TerminalSession", str], None]


def _decode(data: bytes | str) -> str:
    if isinstance(data, str):
        return data
    return data.decode("utf-8", errors="replace")


def _launch_command(command: list[str]) -> list[str]:
    if not command:
        return command
    resolved = shutil.which(command[0])
    if resolved:
        return [resolved, *command[1:]]
    return command


def summarize_failure(stdout: str = "", stderr: str = "", error: str | None = None, limit: int = 1600) -> str:
    text = "\n".join(part for part in [error or "", stderr or "", stdout or ""] if part).strip()
    if not text:
        return ""
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines[-20:])[:limit]


@dataclass
class TerminalSession:
    id: str
    part_id: str
    session_id: str
    command: list[str]
    cwd: str
    interactive: bool
    created_at: float = field(default_factory=time.time)
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    error: str | None = None
    on_output: TerminalOutputCallback | None = None
    _queues: list[tuple[asyncio.Queue[dict[str, Any]], asyncio.AbstractEventLoop]] = field(default_factory=list)
    _history: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=256))
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _process: subprocess.Popen[bytes] | None = None
    _pty: Any | None = None
    _done: threading.Event = field(default_factory=threading.Event)

    @property
    def running(self) -> bool:
        return self.exit_code is None and self.error is None

    def append_output(self, data: str) -> None:
        if not data:
            return
        with self._lock:
            self.stdout = (self.stdout + data)[-MAX_CAPTURE_BYTES:]
        self.publish({"type": "output", "data": data})
        if self.on_output:
            self.on_output(self, data)

    def mark_exit(self, exit_code: int) -> None:
        self.exit_code = exit_code
        self.publish({"type": "exit", "exit_code": exit_code})
        self._done.set()

    def mark_error(self, message: str) -> None:
        self.error = message
        self.publish({"type": "error", "message": message})

    def publish(self, message: dict[str, Any]) -> None:
        with self._lock:
            self._history.append(message)
            queues = list(self._queues)
        for queue, loop in queues:
            def put(target: asyncio.Queue[dict[str, Any]] = queue, item: dict[str, Any] = message) -> None:
                try:
                    target.put_nowait(item)
                except asyncio.QueueFull:
                    pass
            try:
                loop.call_soon_threadsafe(put)
            except RuntimeError:
                self.unsubscribe(queue)

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=1024)
        loop = asyncio.get_running_loop()
        ready = {
            "type": "ready",
            "terminal_id": self.id,
            "part_id": self.part_id,
            "interactive": self.interactive,
            "command": self.command,
            "cwd": self.cwd,
        }
        with self._lock:
            self._queues.append((queue, loop))
            history = [ready, *list(self._history)]
            if self.exit_code is not None:
                history.append({"type": "exit", "exit_code": self.exit_code})
            if self.error:
                history.append({"type": "error", "message": self.error})
        for item in history:
            try:
                queue.put_nowait(item)
            except asyncio.QueueFull:
                break
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        with self._lock:
            self._queues = [(item, loop) for item, loop in self._queues if item is not queue]


class AgentTerminalManager:
    def __init__(self) -> None:
        self._sessions: dict[str, TerminalSession] = {}
        self._lock = threading.Lock()

    def get(self, terminal_id: str) -> TerminalSession | None:
        with self._lock:
            return self._sessions.get(terminal_id)

    def start(
        self,
        *,
        part_id: str,
        session_id: str,
        command: list[str],
        cwd: str | Path,
        timeout_seconds: int = 120,
        on_output: TerminalOutputCallback | None = None,
        on_exit: TerminalExitCallback | None = None,
    ) -> TerminalSession:
        terminal_id = f"agt_{uuid.uuid4().hex}"
        cwd_text = str(Path(cwd).resolve())
        session = TerminalSession(
            id=terminal_id,
            part_id=part_id,
            session_id=session_id,
            command=[str(item) for item in command],
            cwd=cwd_text,
            interactive=False,
            on_output=on_output,
        )
        with self._lock:
            self._sessions[terminal_id] = session

        if os.name == "nt" and self._start_winpty(session, timeout_seconds, on_exit):
            return session
        self._start_popen(session, timeout_seconds, on_exit)
        return session

    def write(self, terminal_id: str, data: str) -> bool:
        session = self.get(terminal_id)
        if not session or not session.running:
            return False
        if session._pty is not None:
            try:
                session._pty.write(data)
                return True
            except Exception as exc:
                session.mark_error(str(exc))
                return False
        process = session._process
        if process and process.stdin:
            try:
                process.stdin.write(data.encode("utf-8", errors="replace"))
                process.stdin.flush()
                return True
            except Exception as exc:
                session.mark_error(str(exc))
        return False

    def resize(self, terminal_id: str, cols: int, rows: int) -> bool:
        session = self.get(terminal_id)
        if not session:
            return False
        if session._pty is not None:
            try:
                if hasattr(session._pty, "setwinsize"):
                    session._pty.setwinsize(rows, cols)
                return True
            except Exception as exc:
                session.mark_error(str(exc))
        return False

    def interrupt(self, terminal_id: str) -> bool:
        session = self.get(terminal_id)
        if not session or not session.running:
            return False
        if session._pty is not None:
            try:
                session._pty.write("\x03")
                return True
            except Exception:
                pass
        process = session._process
        if not process:
            return False
        try:
            if os.name == "nt":
                process.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                process.send_signal(signal.SIGINT)
            return True
        except Exception:
            try:
                process.terminate()
                return True
            except Exception as exc:
                session.mark_error(str(exc))
        return False

    def terminate(self, terminal_id: str) -> bool:
        session = self.get(terminal_id)
        if not session or not session.running:
            return False
        if session._pty is not None:
            try:
                session._pty.terminate()
                return True
            except Exception:
                pass
        process = session._process
        if process:
            process.terminate()
            return True
        return False

    def wait(self, terminal_id: str, timeout: float | None = None) -> TerminalSession | None:
        session = self.get(terminal_id)
        if not session:
            return None
        session._done.wait(timeout)
        return session

    def _start_winpty(
        self,
        session: TerminalSession,
        timeout_seconds: int,
        on_exit: TerminalExitCallback | None,
    ) -> bool:
        try:
            from winpty import PtyProcess  # type: ignore
        except Exception:
            return False
        try:
            command_line = subprocess.list2cmdline(_launch_command(session.command))
            pty = PtyProcess.spawn(command_line, cwd=session.cwd, dimensions=(30, 100))
            session._pty = pty
            session.interactive = True
        except Exception:
            return False

        def reader() -> None:
            deadline = time.monotonic() + timeout_seconds
            exit_code = 0
            try:
                while True:
                    if timeout_seconds > 0 and time.monotonic() > deadline:
                        try:
                            pty.terminate()
                        finally:
                            exit_code = -9
                            break
                    try:
                        data = pty.read(4096)
                    except EOFError:
                        break
                    if data:
                        session.append_output(_decode(data))
                    if hasattr(pty, "isalive") and not pty.isalive():
                        break
                if hasattr(pty, "exitstatus"):
                    value = pty.exitstatus
                    exit_code = int(value) if value is not None else exit_code
            except Exception as exc:
                session.mark_error(str(exc))
                exit_code = 1
            session.mark_exit(exit_code)
            if on_exit:
                on_exit(session)

        threading.Thread(target=reader, name=f"agent-terminal-{session.id}", daemon=True).start()
        return True

    def _start_popen(
        self,
        session: TerminalSession,
        timeout_seconds: int,
        on_exit: TerminalExitCallback | None,
    ) -> None:
        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        try:
            process = subprocess.Popen(
                _launch_command(session.command),
                cwd=session.cwd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                shell=False,
                creationflags=creationflags,
            )
            session._process = process
        except Exception as exc:
            session.mark_error(str(exc))
            session.mark_exit(1)
            if on_exit:
                on_exit(session)
            return

        def reader() -> None:
            timed_out = False
            timer: threading.Timer | None = None

            def kill_timeout() -> None:
                nonlocal timed_out
                timed_out = True
                try:
                    process.kill()
                except Exception:
                    pass

            if timeout_seconds > 0:
                timer = threading.Timer(timeout_seconds, kill_timeout)
                timer.daemon = True
                timer.start()
            try:
                assert process.stdout is not None
                for chunk in iter(lambda: process.stdout.read(4096), b""):
                    session.append_output(_decode(chunk))
                exit_code = process.wait()
                if timed_out:
                    session.append_output(f"\n[command timed out after {timeout_seconds}s]\n")
                    exit_code = -9
                session.mark_exit(int(exit_code))
            except Exception as exc:
                session.mark_error(str(exc))
                session.mark_exit(1)
            finally:
                if timer:
                    timer.cancel()
                if on_exit:
                    on_exit(session)

        threading.Thread(target=reader, name=f"agent-terminal-{session.id}", daemon=True).start()


terminal_manager = AgentTerminalManager()


def terminal_result_payload(session: TerminalSession) -> dict[str, Any]:
    failure = summarize_failure(session.stdout, session.stderr) if session.exit_code else ""
    return {
        "terminal_id": session.id,
        "interactive": session.interactive,
        "command": session.command,
        "cwd": session.cwd,
        "stdout": session.stdout,
        "stderr": session.stderr,
        "exit_code": session.exit_code,
        "failure_summary": failure,
    }
