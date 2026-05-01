# Structure Spec

## Repository Shape
- `src/specode/`: application package
- `tests/`: automated tests around public behavior and session contracts
- `steering/`: durable project memory for product, tech, structure, and focused guidance such as testing
- `tasks/<task-name>/`: task-specific artifacts (`task.md`, `context.md`, `design.md`, `tasks.md`)
- Root docs such as `README.md`: user-facing setup and project overview

## Entry Points
- `src/specode/cli.py`: Typer application and top-level runtime loop
- `specode` console script from `pyproject.toml`
- `/steering` is an in-session command routed by `cli.py` before normal chat prompts.

## Architectural Conventions
- `cli.py` should orchestrate startup and session flow, not own deep business logic.
- `config.py` owns environment loading and validation.
- `input.py` owns prompt-toolkit setup, slash-command completion, and terminal input fallback behavior.
- `session.py` owns in-memory session state, prompt interpretation, and session-level behavior.
- `agent.py` owns the model-facing adapter boundary.
- `repository.py` owns safe, bounded, redacted repository inspection for model-visible project research.
- `steering.py` owns steering proposal validation, approval-gated write semantics, and foundational steering file constraints.
- `ui.py` owns Rich rendering and terminal prompts.
- Keep dependencies flowing inward from CLI to session/config/agent/UI; avoid circular knowledge between presentation and model code.

## Module Contract
- A new runtime module should have one clear responsibility and expose a small public surface.
- External integrations belong behind adapter-style boundaries rather than leaking library details through the app.
- Model-visible repository research should go through `RepositoryInspector` rather than direct filesystem access.
- Steering write behavior should go through `SteeringWorkflow`/`SteeringStore` so validation, staging, rollback, and path limits stay centralized.
- Tests should prefer command or session boundaries over helper internals.

## Module Interface Map
- CLI shell: `specode.cli` owns Typer wiring, startup orchestration, slash-command routing, and terminal lifecycle. Callers rely on the `specode` command and `main()` entrypoint; tests should assert visible CLI behavior, exit codes, and approved side effects rather than Rich rendering details or loop internals. Changes to command names, process exit behavior, or prompt flow need CLI and e2e review.
- Session behavior: `SessionController`, `SessionCommand`, and command metadata own in-memory transcript state, slash-command interpretation, and chat turn storage. Callers rely on `interpret()`, `clear()`, `respond_to()`, `get_command_infos()`, and `find_matching_commands()`; tests should not depend on private transcript mutation order beyond public session outcomes. Changes to supported commands, message history shape, or transcript semantics need session and CLI review.
- Model adapter: `ChatService` and `SteeringDraftService` are the stable boundaries for model-backed work. Runtime code should depend on those protocols and normalized outputs, not Pydantic AI call mechanics, prompts, retry details, or provider response internals. Changes to these protocols or model-visible request shape need adapter tests with fakes.
- Repository inspection: `RepositoryInspector` and `WorkspacePolicy` own safe, bounded, redacted reads/searches for model-visible project evidence. Callers rely on `list_files()`, `read_file()`, and `search_text()` returning redacted structured data; callers must not bypass path policy, ignored-file rules, size limits, or secret filtering. Changes to safety policy, redaction, or path handling need repository behavior tests.
- Steering workflow: `SteeringWorkflow`, `SteeringStore`, and steering proposal dataclasses own proposal validation and approval-gated writes to foundational docs. Callers rely on `prepare()` writing nothing and `apply()` staging all changes before replacing files; tests must not depend on temp-file names, helper call order, or rollback mechanics. Changes to allowed paths, validation rules, or write semantics need steering contract tests and CLI approval-flow coverage.
- Terminal UI/input: `InputHandler` owns prompt-toolkit completion/fallback behavior, and `ui.py` owns Rich output helpers. Callers rely on command completion and visible text contracts; tests should assert stable substrings and completion results, not ANSI minutiae. Changes to interactive input, Tab completion, or interrupt handling need PTY coverage when `CliRunner` cannot prove the behavior.

## Where To Put New Work
- New application code: `src/specode/`
- New tests: `tests/`
- New steering docs: `steering/`
- New feature/task planning artifacts: `tasks/<task-name>/`, without mixing them into `steering/`
