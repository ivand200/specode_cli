# specode

`specode` is an opinionated terminal framework for reliable AI-assisted software development.

It starts as a terminal-first AI chat assistant built with Python, Typer, Rich, and Pydantic AI. The product direction is to bring Rails/Django-like conventions to agentic coding: durable steering docs, feature-scoped specs, reusable skills, and approval-gated workflows.

This repository is being built through a spec-driven workflow. The current milestone includes a working interactive CLI chat loop with terminal controls, startup configuration checks, project steering support, and test coverage around the main public behavior.

## Requirements

- Python 3.10 or newer
- `uv`
- `OPENAI_API_KEY`

## Setup

1. Create a local `.env` file:

```env
OPENAI_API_KEY=your-api-key-here
```

2. Install dependencies:

```bash
uv sync
```

## Run

For local development:

```bash
uv run specode
```

If the package is installed in an environment that exposes console scripts, you can also run:

```bash
specode
```

## Install as a Global Tool

Install SpeCode from GitHub with `uv`:

```bash
uv tool install git+https://github.com/ivand200/specode_cli.git
```

After installing, run `specode` from any project directory:

```bash
specode
```

To update an existing install:

```bash
uv tool upgrade specode --reinstall
```

If `uv` reports that `specode` is already installed and you want to reinstall directly from GitHub:

```bash
uv tool install --force --reinstall git+https://github.com/ivand200/specode_cli.git
```

## Current Status

- The `specode` command launches an interactive terminal session.
- `OPENAI_API_KEY` is validated at startup with an actionable error if it is missing.
- `/help`, `/clear`, `/exit`, and `/quit` are available as in-session controls.
- `/steering` inspects the current project, previews foundational steering doc changes, and writes only after explicit approval.
- In an interactive terminal, typing `/` reveals the available slash commands and `Tab` completes partial commands such as `/ex`.
- Responses are generated through a Pydantic AI-backed chat service.

## Project Workflow

- `steering/` holds durable project memory: product, tech, and structure.
- The `/steering` workflow can create or refresh `steering/product.md`, `steering/tech.md`, and `steering/structure.md` after showing the proposed changes and receiving `y` or `yes` approval.
- `tasks/<task-name>/` holds task-specific artifacts: `task.md`, `context.md`, `design.md`, and `tasks.md`.
- The workflow is intentionally small: clarify the task, design when useful, break work into slices, implement, review, and test.
