# Structure Spec

## Repository Shape
- `src/specode/`: application package
- `tests/`: automated tests around public behavior and session contracts
- `steering/`: durable project memory for product, tech, and structure guidance
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

## Where To Put New Work
- New application code: `src/specode/`
- New tests: `tests/`
- New steering docs: `steering/`
- New feature/task planning artifacts: `tasks/<task-name>/`, without mixing them into `steering/`
