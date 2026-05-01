"""Process-level end-to-end tests for the packaged specode CLI."""

from __future__ import annotations

from collections.abc import Mapping
import os
from pathlib import Path
import subprocess

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
COMMAND = ["uv", "run", "specode"]
PROCESS_TIMEOUT_SECONDS = 5

pytestmark = pytest.mark.e2e


def _run_specode(
    tmp_path: Path,
    *,
    stdin: str,
    extra_env: Mapping[str, str],
    timeout_seconds: int = PROCESS_TIMEOUT_SECONDS,
) -> tuple[subprocess.CompletedProcess[str], dict[str, str]]:
    env = _isolated_env(tmp_path, extra_env=extra_env)

    try:
        result = subprocess.run(
            COMMAND,
            cwd=REPO_ROOT,
            env=env,
            input=stdin,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        pytest.fail(_format_diagnostics(env, stdout, stderr, returncode="timeout"))

    return result, env


def _isolated_env(tmp_path: Path, *, extra_env: Mapping[str, str]) -> dict[str, str]:
    env = {
        "HOME": str(tmp_path),
        "PATH": os.environ["PATH"],
        "PYTHONUNBUFFERED": "1",
        "TERM": "dumb",
        "TMPDIR": str(tmp_path),
        "USERPROFILE": str(tmp_path),
    }
    env.update(extra_env)
    return env


def _format_diagnostics(
    env: Mapping[str, str], stdout: str, stderr: str, *, returncode: int | str
) -> str:
    env_snapshot = {
        key: env.get(key, "<missing>")
        for key in ("OPENAI_API_KEY", "HOME", "PATH", "TERM", "TMPDIR")
    }
    return (
        f"Command: {' '.join(COMMAND)}\n"
        f"CWD: {REPO_ROOT}\n"
        f"Return code: {returncode}\n"
        f"Environment: {env_snapshot}\n"
        f"STDOUT:\n{stdout}\n"
        f"STDERR:\n{stderr}"
    )


def test_specode_exits_with_configuration_error_when_openai_api_key_is_missing(
    tmp_path: Path,
) -> None:
    result, env = _run_specode(tmp_path, stdin="", extra_env={"OPENAI_API_KEY": ""})
    diagnostics = _format_diagnostics(env, result.stdout, result.stderr, returncode=result.returncode)

    assert result.returncode == 1, diagnostics
    assert "Configuration Error" in result.stdout, diagnostics
    assert "Missing OPENAI_API_KEY" in result.stdout, diagnostics


def test_specode_handles_help_then_exit_without_calling_a_model(tmp_path: Path) -> None:
    result, env = _run_specode(
        tmp_path,
        stdin="/help\n/exit\n",
        extra_env={"OPENAI_API_KEY": "test-key"},
    )
    diagnostics = _format_diagnostics(env, result.stdout, result.stderr, returncode=result.returncode)

    assert result.returncode == 0, diagnostics
    assert "Type / for commands" in result.stdout, diagnostics
    assert "Show available session controls" in result.stdout, diagnostics
    assert "/steering" in result.stdout, diagnostics
    assert "Goodbye from specode." in result.stdout, diagnostics
