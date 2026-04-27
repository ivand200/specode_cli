from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

from specode.agent import ChatReply
from specode.session import SessionCommand, SessionController


class FakeChatService:
    def reply(self, prompt: str, history: list[ModelRequest | ModelResponse]) -> ChatReply:
        return ChatReply(
            text=f"Assistant reply to {prompt}",
            new_messages=[
                ModelRequest(parts=[UserPromptPart(content=prompt)]),
                ModelResponse(parts=[TextPart(content=f"Assistant reply to {prompt}")]),
            ],
        )


def test_interprets_slash_commands_case_insensitively() -> None:
    session = SessionController()

    result = session.interpret("/ClEaR")

    assert result is SessionCommand.CLEAR


def test_interprets_steering_case_insensitively() -> None:
    session = SessionController()

    result = session.interpret("/Steering")

    assert result is SessionCommand.STEERING


def test_treats_steering_with_arguments_as_a_normal_prompt() -> None:
    session = SessionController()

    result = session.interpret("/steering now")

    assert result == "/steering now"


def test_records_a_prompt_and_assistant_reply_in_session_state() -> None:
    session = SessionController()

    reply = session.respond_to("Hello", FakeChatService())

    assert reply == "Assistant reply to Hello"
    assert [message.role for message in session.state.transcript] == ["user", "assistant"]


def test_treats_unknown_slash_input_as_a_normal_prompt() -> None:
    session = SessionController()

    result = session.interpret("/explain")

    assert result == "/explain"


def test_clear_resets_the_transcript_and_model_history() -> None:
    session = SessionController()
    session.respond_to("Hello", FakeChatService())

    session.clear()

    assert session.state.transcript == []
    assert session.state.message_history == []
