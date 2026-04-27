# Product Spec

## Purpose
- `specode` is a terminal-first AI chat assistant.
- It is evolving toward an opinionated CLI agent framework for spec-first AI development.
- The long-term product direction is closer to a framework than a generic chatbot: it should guide users through durable conventions, structured artifacts, and repeatable workflows.

## Users / Actors
- Primary user: a developer working in the terminal who wants to chat with an AI assistant.
- Future user: a developer who wants Rails/Django-like workflow guidance for agentic coding rather than assembling prompts, docs, and tools by hand.
- External actor: an OpenAI-backed model accessed through Pydantic AI.

## Core Workflows
- Start the app by running `specode` or `uv run specode`.
- Chat with the assistant in the same terminal session.
- Use in-session controls such as `/help`, `/clear`, `/steering`, `/exit`, and `/quit`.
- Use `/steering` to inspect the current project, preview foundational steering doc changes, and write them only after explicit approval.
- Receive a clear startup error if required configuration is missing.

## Core Domain Concepts
- Session: one in-memory terminal conversation for the current process.
- Transcript: the user and assistant messages shown during that session.
- Chat service: the model-facing boundary that turns a prompt plus session history into one assistant reply.
- Steering docs: durable project-level memory in `steering/product.md`, `steering/tech.md`, and `steering/structure.md`.
- Steering proposal: a previewable, validated set of foundational doc changes that can be accepted or rejected.
- Specs: feature- or bug-scoped artifacts that capture requirements, design, and implementation slices.
- Skills: reusable, on-demand workflow packages that shape how the agent clarifies, plans, executes, reviews, or tests work.

## Scope Boundaries
- No persistent chat history across runs.
- No multi-provider or account system yet.
- No full-screen terminal IDE or pane-based TUI.
- `/steering` is limited to foundational project steering; task plans and implementation artifacts stay outside the product workflow for now.
- The framework should stay opinionated without becoming a heavyweight project-management system.

## Durable Constraints
- `specode` remains the primary command and user-facing entrypoint.
- The app should feel calm and readable in the terminal, not noisy or overly complex.
- `OPENAI_API_KEY` is the only required runtime secret for the current product shape.
- Steering changes must be previewed and explicitly approved before files are written.
