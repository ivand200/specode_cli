"""Terminal-native input handling for specode."""

from __future__ import annotations

from dataclasses import dataclass, field
import sys
from typing import Iterable

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.shortcuts import CompleteStyle
from rich.console import Console

from specode.session import CommandInfo, find_matching_commands, get_command_infos


PROMPT_LABEL = "[bold cyan]>[/bold cyan] "


class SlashCommandCompleter(Completer):
    """Autocomplete slash commands while the user is typing."""

    def __init__(self, commands: Iterable[CommandInfo]) -> None:
        self._commands = tuple(commands)

    def get_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> Iterable[Completion]:
        text = document.text_before_cursor.strip()
        if not text.startswith("/") or " " in text:
            return

        for info in find_matching_commands(text):
            yield Completion(
                text=info.command.value,
                start_position=-len(text),
                display=info.command.value,
                display_meta=info.description,
            )


@dataclass
class InputHandler:
    """Own the terminal input experience for specode."""

    commands: tuple[CommandInfo, ...] = field(default_factory=get_command_infos)
    _session: PromptSession[str] | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        if self._supports_advanced_input():
            self._session = PromptSession(
                completer=SlashCommandCompleter(self.commands),
                complete_while_typing=True,
                complete_style=CompleteStyle.COLUMN,
                history=InMemoryHistory(),
                key_bindings=_build_prompt_bindings(),
            )

    def prompt(self, console: Console) -> str:
        """Read one line of input, using richer completion when possible."""
        if self._session is None:
            return console.input(PROMPT_LABEL)

        return self._session.prompt("> ")

    @staticmethod
    def _supports_advanced_input() -> bool:
        return sys.stdin.isatty() and sys.stdout.isatty()


def _build_prompt_bindings() -> KeyBindings:
    """Prevent empty submits from consuming vertical space."""
    bindings = KeyBindings()

    @bindings.add("enter", eager=True)
    def _handle_enter(event) -> None:
        buffer = event.current_buffer
        if not buffer.text.strip():
            return

        buffer.validate_and_handle()

    return bindings
