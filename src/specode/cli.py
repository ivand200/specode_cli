"""CLI entrypoint for the specode application."""

from pathlib import Path

import typer

from specode.agent import (
    ChatService,
    ChatServiceError,
    PydanticAIChatService,
    PydanticAISteeringDraftService,
    SteeringDraftServiceError,
)
from specode.config import ConfigurationError, load_settings
from specode.input import InputHandler
from specode.session import SessionCommand, SessionController
from specode.steering import SteeringValidationError, SteeringWorkflow, SteeringWorkflowError
from specode.ui import (
    build_console,
    render_assistant_message,
    render_configuration_error,
    render_goodbye,
    render_help,
    render_no_steering_updates,
    render_reset_hint,
    render_runtime_error,
    render_steering_apply_result,
    render_steering_error,
    render_steering_phase,
    render_steering_proposal,
    render_steering_rejected,
    render_user_message,
    render_welcome,
)


app = typer.Typer(
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
    help="Launch the specode terminal assistant.",
)


def create_chat_service() -> ChatService:
    """Create the runtime chat service."""
    return PydanticAIChatService()


def create_steering_workflow(project_root: Path | str | None = None) -> SteeringWorkflow:
    """Create the runtime steering workflow."""
    return SteeringWorkflow(
        project_root or Path.cwd(),
        draft_service=PydanticAISteeringDraftService(),
    )


@app.callback(invoke_without_command=True)
def run() -> None:
    """Launch the current specode experience."""
    console = build_console()

    try:
        settings = load_settings()
    except ConfigurationError as exc:
        render_configuration_error(console, str(exc))
        raise typer.Exit(code=1) from exc

    render_welcome(console, settings.model_name)
    session = SessionController()
    input_handler = InputHandler()
    chat_service = create_chat_service()

    while True:
        try:
            raw_input = input_handler.prompt(console)
        except (EOFError, KeyboardInterrupt):
            console.print()
            render_goodbye(console)
            raise typer.Exit(code=0) from None

        action = session.interpret(raw_input)
        if action is None:
            continue

        if action is SessionCommand.HELP:
            render_help(console)
            continue

        if action is SessionCommand.CLEAR:
            session.clear()
            console.clear()
            render_reset_hint(console)
            continue

        if action is SessionCommand.STEERING:
            _run_steering_command(console, input_handler)
            continue

        if action in {SessionCommand.EXIT, SessionCommand.QUIT}:
            render_goodbye(console)
            raise typer.Exit(code=0)

        render_user_message(console, action)

        try:
            with console.status("[bold cyan]specode is thinking...[/bold cyan]"):
                reply = session.respond_to(action, chat_service)
        except ChatServiceError as exc:
            render_runtime_error(console, str(exc))
            continue

        render_assistant_message(console, reply)


def main() -> None:
    """Run the Typer application."""
    app()


def _run_steering_command(console, input_handler: InputHandler) -> None:
    workflow = create_steering_workflow()

    try:
        render_steering_phase(console, "Preparing steering proposal...")
        prepared = workflow.prepare()
    except (
        SteeringDraftServiceError,
        SteeringValidationError,
        SteeringWorkflowError,
        OSError,
    ) as exc:
        render_steering_error(console, str(exc))
        return

    if not prepared.proposal.changes:
        render_no_steering_updates(console)
        return

    render_steering_proposal(console, prepared.proposal)
    answer = console.input("[bold cyan]Apply these steering changes? \\[y/N][/bold cyan] ")
    if answer.strip().lower() not in {"y", "yes"}:
        render_steering_rejected(console)
        return

    try:
        result = workflow.apply(prepared)
    except (SteeringValidationError, OSError) as exc:
        render_steering_error(console, str(exc))
        return

    render_steering_apply_result(console, result)
