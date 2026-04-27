"""Rich-powered terminal presentation for specode."""

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from specode.session import get_command_infos
from specode.steering import SteeringApplyResult, SteeringFileProposal, SteeringProposal


def build_console() -> Console:
    """Create the shared Rich console for specode."""
    return Console()


def render_welcome(console: Console, model_name: str) -> None:
    """Render the startup welcome state."""
    wordmark = Text()
    wordmark.append("Spe", style="bold white")
    wordmark.append("CODE", style="bold cyan")

    console.print(wordmark)
    console.print("[dim]Terminal-first AI chat that stays compact and keyboard-friendly.[/dim]")
    console.print(f"[dim]Model:[/dim] [cyan]{model_name}[/cyan]")
    console.print("[dim]Type / for commands, press Tab to complete, or Ctrl-D to exit.[/dim]")
    console.print()


def render_reset_hint(console: Console) -> None:
    """Render a small post-clear anchor without replaying the full splash."""
    console.print("[dim]Cleared. Type / for commands.[/dim]")
    console.print()


def render_help(console: Console) -> None:
    """Render the in-session help text."""
    console.print("[bold cyan]Commands[/bold cyan]")
    for info in get_command_infos():
        console.print(f"{info.command.value:<7} {info.description}")
    console.print()


def render_configuration_error(console: Console, message: str) -> None:
    """Render a calm startup error for missing configuration."""
    console.print(
        Panel.fit(
            message,
            title="Configuration Error",
            border_style="red",
            padding=(1, 2),
        )
    )


def render_runtime_error(console: Console, message: str) -> None:
    """Render a recoverable runtime error inside the session."""
    console.print(
        Panel.fit(
            message,
            title="Reply Error",
            border_style="red",
            padding=(1, 2),
        )
    )


def render_steering_error(console: Console, message: str) -> None:
    """Render a recoverable steering workflow error."""
    console.print(
        Panel.fit(
            message,
            title="Steering Error",
            border_style="red",
            padding=(1, 2),
        )
    )


def render_steering_phase(console: Console, message: str) -> None:
    """Render one compact steering workflow phase."""
    console.print(f"[dim]{message}[/dim]")


def render_steering_proposal(console: Console, proposal: SteeringProposal) -> None:
    """Render a compact preview of proposed steering changes."""
    console.print("[bold cyan]Steering Proposal[/bold cyan]")
    if proposal.summary:
        console.print(proposal.summary)

    for note in proposal.notes:
        console.print(f"[dim]- {note}[/dim]")

    for change in proposal.changes:
        _render_steering_change(console, change)
    console.print()


def render_no_steering_updates(console: Console) -> None:
    """Render a no-op steering result."""
    console.print("[dim]No steering updates needed.[/dim]")
    console.print()


def render_steering_rejected(console: Console) -> None:
    """Render the result of a rejected steering proposal."""
    console.print("[dim]No steering files changed.[/dim]")
    console.print()


def render_steering_apply_result(console: Console, result: SteeringApplyResult) -> None:
    """Render changed steering files after approval."""
    console.print("[bold green]Steering files changed[/bold green]")
    for changed in result.changed_files:
        detail = f" - {changed.reason}" if changed.reason else ""
        console.print(f"{changed.path} ({changed.action}){detail}")
    console.print()


def render_user_message(console: Console, message: str) -> None:
    """Render a user prompt in the session transcript."""
    _render_chat_message(console, speaker=">", speaker_style="bold cyan", message=message)


def render_assistant_message(console: Console, message: str) -> None:
    """Render an assistant reply in the session transcript."""
    _render_chat_message(console, speaker="SpeCODE", speaker_style="bold green", message=message)


def render_goodbye(console: Console) -> None:
    """Render a short session exit message."""
    console.print("[dim]Goodbye from specode.[/dim]")


def _render_chat_message(
    console: Console, *, speaker: str, speaker_style: str, message: str
) -> None:
    """Render one compact transcript entry."""
    entry = Text()
    entry.append(f"{speaker} > ", style=speaker_style)
    entry.append(message)
    console.print(entry)
    console.print()


def _render_steering_change(console: Console, change: SteeringFileProposal) -> None:
    console.print()
    console.print(f"[cyan]{change.path}[/cyan] [dim]({change.action})[/dim]")
    if change.reason:
        console.print(f"[dim]{change.reason}[/dim]")

    if change.action in {"create", "replace"}:
        console.print(
            Panel(
                change.content,
                title="Proposed content",
                border_style="cyan",
            )
        )
        return

    for index, edit in enumerate(change.edits, start=1):
        if edit.reason:
            console.print(f"[dim]Edit {index}: {edit.reason}[/dim]")
        console.print(Panel(edit.old_text, title="Old", border_style="red"))
        console.print(Panel(edit.new_text, title="New", border_style="green"))
