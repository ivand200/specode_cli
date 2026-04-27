"""Session state and behavior for specode."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Final

from pydantic_ai.messages import ModelMessage

from specode.agent import ChatService


class SessionCommand(str, Enum):
    """Supported in-session commands."""

    HELP = "/help"
    CLEAR = "/clear"
    STEERING = "/steering"
    EXIT = "/exit"
    QUIT = "/quit"


@dataclass(frozen=True)
class CommandInfo:
    """User-facing metadata for an in-session slash command."""

    command: SessionCommand
    description: str


@dataclass(frozen=True)
class TranscriptMessage:
    """A rendered message in the current terminal session."""

    role: str
    content: str


@dataclass
class SessionState:
    """Mutable in-memory session state for the current process."""

    transcript: list[TranscriptMessage] = field(default_factory=list)
    message_history: list[ModelMessage] = field(default_factory=list)


COMMAND_INFOS: Final[tuple[CommandInfo, ...]] = (
    CommandInfo(SessionCommand.HELP, "Show available session controls"),
    CommandInfo(SessionCommand.CLEAR, "Clear the current transcript"),
    CommandInfo(SessionCommand.STEERING, "Create or refresh project steering docs"),
    CommandInfo(SessionCommand.EXIT, "Exit the session"),
    CommandInfo(SessionCommand.QUIT, "Exit the session"),
)


def get_command_infos() -> tuple[CommandInfo, ...]:
    """Return the supported slash commands with their help text."""
    return COMMAND_INFOS


def find_matching_commands(raw_input: str) -> tuple[CommandInfo, ...]:
    """Return slash commands that match the current input prefix."""
    text = raw_input.strip().lower()
    if not text.startswith("/"):
        return ()

    if text == "/":
        return COMMAND_INFOS

    return tuple(info for info in COMMAND_INFOS if info.command.value.startswith(text))


class SessionController:
    """Own the interactive session state and command interpretation."""

    def __init__(self) -> None:
        self.state = SessionState()

    def interpret(self, raw_input: str) -> SessionCommand | str | None:
        """Normalize raw terminal input into a command or prompt."""
        text = raw_input.strip()
        if not text:
            return None

        normalized = text.lower()
        for command in SessionCommand:
            if normalized == command.value:
                return command

        return text

    def clear(self) -> None:
        """Reset the in-memory session state."""
        self.state = SessionState()

    def respond_to(self, prompt: str, chat_service: ChatService) -> str:
        """Store one prompt/response turn and return the assistant text."""
        self.state.transcript.append(TranscriptMessage(role="user", content=prompt))
        reply = chat_service.reply(prompt, list(self.state.message_history))
        self.state.message_history.extend(reply.new_messages)
        self.state.transcript.append(TranscriptMessage(role="assistant", content=reply.text))
        return reply.text
