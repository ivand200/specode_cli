from prompt_toolkit.document import Document

from specode.input import SlashCommandCompleter
from specode.session import get_command_infos


def test_reveals_all_available_commands_when_input_starts_with_slash() -> None:
    completer = SlashCommandCompleter(get_command_infos())
    completions = list(completer.get_completions(Document("/", cursor_position=1), None))

    assert [completion.text for completion in completions] == [
        "/help",
        "/clear",
        "/steering",
        "/exit",
        "/quit",
    ]


def test_suggests_exit_for_a_partial_exit_command() -> None:
    completer = SlashCommandCompleter(get_command_infos())

    completions = list(completer.get_completions(Document("/ex", cursor_position=3), None))

    assert [completion.text for completion in completions] == ["/exit"]


def test_suggests_steering_for_a_partial_steering_command() -> None:
    completer = SlashCommandCompleter(get_command_infos())

    completions = list(completer.get_completions(Document("/ste", cursor_position=4), None))

    assert [completion.text for completion in completions] == ["/steering"]
