# Tech Spec

## Stack
- Python 3.10+
- `uv` for dependency and environment management
- Typer for the CLI entrypoint
- Rich for terminal rendering
- `prompt-toolkit` for interactive input, slash-command suggestions, and command completion
- Pydantic AI for model integration
- `python-dotenv` for local environment loading

## Key Services / Infrastructure
- OpenAI-compatible model access through Pydantic AI
- Local `.env` support for development configuration
- Pydantic AI-backed steering draft service with read-only repository inspection tools
- Approval-gated steering store that writes only foundational steering docs and stages changes before applying them
- No database, queue, auth system, or persistent storage at this stage

## Engineering Conventions
- Keep module responsibilities narrow: CLI orchestration, config loading, session behavior, model adapter, and UI rendering should stay separate.
- Prefer simple synchronous control flow unless requirements force something more complex.
- Test public behavior at stable boundaries such as the CLI command and session workflow.
- Follow the dedicated testing guidance in `steering/testing.md` for unit, CLI, process e2e, and PTY e2e coverage.
- Keep repository inspection bounded, redacted, and read-only when exposing project evidence to a model.
- Use `pytest` for tests and `ruff` for linting.
- When working with Pydantic AI, use the official docs reference at https://pydantic.dev/docs/ai/llms.txt as a primary source for current API and integration guidance.

## Related Steering Docs
- [Product Spec](/Users/ivandubograi/Documents/ai_practice/cli_agent_4/steering/product.md)
- [Structure Spec](/Users/ivandubograi/Documents/ai_practice/cli_agent_4/steering/structure.md)
- [Testing Spec](/Users/ivandubograi/Documents/ai_practice/cli_agent_4/steering/testing.md)

## Technical Constraints
- Do not require more than `OPENAI_API_KEY` unless product direction changes.
- Avoid speculative provider abstractions, persistence layers, or plugin systems before there is real need.
- Treat `.env` as local-only developer configuration and keep it ignored by version control.
- Steering writes are constrained to `steering/product.md`, `steering/tech.md`, and `steering/structure.md`; custom steering docs are background context only.
