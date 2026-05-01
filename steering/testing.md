# Testing Spec

## Purpose
- Testing should prove user-visible behavior and stable contracts without making the suite slow, flaky, or dependent on real third-party services.
- The test strategy should make `specode` feel reliable as both imported Python code and a real terminal CLI.
- This doc is durable project guidance for unit, CLI, process e2e, and terminal e2e tests.

## Testing Layers
- Unit and behavior tests prove rules in focused modules such as `session.py`, `config.py`, `repository.py`, `steering.py`, and `input.py`.
- `CliRunner` tests prove Typer command wiring, command routing, rendered output, and recoverable errors without spawning a real process.
- Process e2e tests prove the packaged command path, subprocess IO, startup configuration, slash-command workflows, and clean exits.
- PTY e2e tests prove behavior that depends on real TTY detection or prompt-toolkit, such as Tab completion and interrupt handling.
- Snapshot-style tests are useful only for stable user-visible terminal output; normalize ANSI/control sequences before snapshotting.

## Unit / Behavior Test Guidance
- Prefer tests at stable public boundaries over helper internals.
- Name tests around observable behavior, not implementation details.
- Arrange with small fakes or fixtures, perform one meaningful action, and assert one or two meaningful outcomes.
- For business rules, keep setup explicit enough that the expected behavior is readable without knowing the implementation.
- When testing model-facing behavior, fake the adapter boundary and assert request shape or normalized response handling, not provider behavior.
- Do not preserve low-value tests that only mirror private helper code; rewrite them around useful contracts.

## CLI Test Guidance
- Use `CliRunner` for fast in-process CLI behavior: help text, startup errors, command routing, approval prompts, and fake service responses.
- Use subprocess e2e when the real console script, package entrypoint, environment isolation, or process exit behavior matters.
- Use PTY tests only for terminal-native behavior that `CliRunner` cannot honestly prove.
- Keep CLI assertions to stable visible substrings, exit codes, and side effects; avoid brittle exact matches against Rich or prompt-toolkit rendering.
- Include useful diagnostics on e2e failures: command, cwd, return code, stdout/stderr, and PTY transcript when available.

## E2E Test Guidance
- E2E tests must never perform real model calls or real third-party provider requests.
- E2E tests may later validate provider request schemas, but only through local fakes, mocks, recorded-safe fixtures, or adapter-level assertions.
- Prefer slash-command scenarios for early e2e because they can exercise the CLI shell without requiring model responses.
- Process e2e should run by default only while it stays fast and deterministic.
- PTY e2e should be explicitly selectable because it is platform-sensitive and easier to flake.
- Every subprocess or PTY test needs a timeout and graceful cleanup.
- Skip PTY tests clearly when dependencies or platform support are unavailable; never let a terminal test hang.
- Use temporary directories and isolated environment variables so local credentials and user configuration do not affect tests.

## Marker / Command Policy
- Default check: `uv run pytest`.
- Full lint check: `uv run ruff check`.
- Process e2e may be included in default pytest when fast and stable.
- PTY e2e should use a marker such as `@pytest.mark.pty` and run explicitly, for example `uv run pytest -m pty`.
- Broader e2e selection should use a marker such as `@pytest.mark.e2e`.

## Reference Lessons
- Gemini CLI and Qwen Code run integration tests explicitly against a built CLI in controlled environments and provide diagnostics such as kept output and verbose logs.
- Gemini CLI also treats memory and performance regression tests as separate suites with baselines, not as ordinary default tests.
- Qwen Code documents sandbox-matrix integration runs and per-test output directories, which is a good model for future filesystem or tool-permission workflows.
- Codex CLI guidance favors scoped package tests, stable user-visible UI snapshots where appropriate, and mocked model responses instead of real provider calls.
- OpenCode exposes separate interactive, non-interactive, and server command surfaces; `specode` should preserve similarly testable boundaries as it grows.

## Current Project Defaults
- Keep most coverage in unit/behavior and `CliRunner` tests.
- Add only a small number of e2e tests for the CLI shell contract.
- Do not add normal chat prompt e2e until there is a local fake model boundary or request-schema harness.
- Treat the first `tests/e2e/test_cli_process.py` and `tests/e2e/test_terminal_pty.py` files as the reference pattern for future CLI e2e tests.

## Source References
- Gemini CLI integration tests: https://geminicli.com/docs/integration-tests/
- Qwen Code integration tests: https://qwenlm.github.io/qwen-code-docs/en/developers/development/integration-tests/
- Codex CLI repository guidance: https://raw.githubusercontent.com/openai/codex/main/AGENTS.md
- OpenCode CLI command surfaces: https://opencode.ai/docs/cli/
