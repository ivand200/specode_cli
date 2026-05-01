"""PTY-backed end-to-end coverage for terminal-native specode behavior."""

from __future__ import annotations

import io
import os
from pathlib import Path
import re
import sys

import pytest


pytestmark = [pytest.mark.e2e, pytest.mark.pty]

if sys.platform == "win32":
    pytest.skip("PTY e2e tests require POSIX pseudo-terminal support.", allow_module_level=True)

pexpect = pytest.importorskip("pexpect", reason="pexpect is required for PTY e2e tests.")

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMAND = "uv run specode"
PTY_TIMEOUT_SECONDS = 4
ANSI_ESCAPE_PATTERN = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1B\\))")


def _isolated_env(tmp_path: Path) -> dict[str, str]:
    return {
        "HOME": str(tmp_path),
        "OPENAI_API_KEY": "test-key",
        "PATH": os.environ["PATH"],
        "PYTHONUNBUFFERED": "1",
        "TERM": "xterm-256color",
        "TMPDIR": str(tmp_path),
        "USERPROFILE": str(tmp_path),
    }


def _normalize_terminal_output(text: str) -> str:
    return ANSI_ESCAPE_PATTERN.sub("", text).replace("\r", "")


def _format_diagnostics(transcript: str, env: dict[str, str], *, exitstatus: int | str) -> str:
    env_snapshot = {
        key: env.get(key, "<missing>")
        for key in ("OPENAI_API_KEY", "HOME", "PATH", "TERM", "TMPDIR")
    }
    return (
        f"Command: {COMMAND}\n"
        f"CWD: {REPO_ROOT}\n"
        f"Exit status: {exitstatus}\n"
        f"Environment: {env_snapshot}\n"
        f"Transcript:\n{transcript}"
    )


def test_tab_completion_completes_exit_and_exits_cleanly(tmp_path: Path) -> None:
    env = _isolated_env(tmp_path)
    transcript = io.StringIO()

    try:
        child = pexpect.spawn(
            COMMAND,
            cwd=str(REPO_ROOT),
            env=env,
            encoding="utf-8",
            echo=False,
            timeout=PTY_TIMEOUT_SECONDS,
        )
    except (OSError, pexpect.exceptions.ExceptionPexpect) as exc:
        pytest.skip(f"Unable to start PTY-backed specode session: {exc}")

    child.logfile = transcript

    try:
        child.expect(">", timeout=PTY_TIMEOUT_SECONDS)
        child.send("/ex")
        child.send("\t")
        child.send("\r")
        child.expect(pexpect.EOF, timeout=PTY_TIMEOUT_SECONDS)
    except pexpect.TIMEOUT:
        normalized = _normalize_terminal_output(transcript.getvalue())
        pytest.fail(_format_diagnostics(normalized, env, exitstatus="timeout"))
    finally:
        child.close(force=True)

    normalized = _normalize_terminal_output(transcript.getvalue())
    diagnostics = _format_diagnostics(normalized, env, exitstatus=child.exitstatus)

    assert child.exitstatus == 0, diagnostics
    assert "/exit" in normalized, diagnostics
    assert "Goodbye from specode." in normalized, diagnostics
