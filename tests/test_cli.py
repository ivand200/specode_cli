from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart
from typer.testing import CliRunner

import specode.cli as cli_module
from specode.agent import ChatReply
from specode.cli import app
from specode.steering import (
    PreparedSteeringProposal,
    SteeringAppliedFile,
    SteeringApplyResult,
    SteeringFileProposal,
    SteeringProposal,
    SteeringValidationError,
    SteeringWorkflowError,
)


runner = CliRunner()


class FakeChatService:
    def reply(self, prompt: str, history: list[ModelRequest | ModelResponse]) -> ChatReply:
        return ChatReply(
            text=f"Echo: {prompt}",
            new_messages=[
                ModelRequest(parts=[UserPromptPart(content=prompt)]),
                ModelResponse(parts=[TextPart(content=f"Echo: {prompt}")]),
            ],
        )


class ErroringChatService:
    def reply(self, prompt: str, history: list[ModelRequest | ModelResponse]) -> ChatReply:
        raise cli_module.ChatServiceError("Temporary failure")


class FakeSteeringWorkflow:
    def __init__(
        self,
        proposal: SteeringProposal,
        *,
        prepare_error: Exception | None = None,
        apply_error: Exception | None = None,
    ) -> None:
        self.proposal = proposal
        self.prepare_error = prepare_error
        self.apply_error = apply_error
        self.applied = False

    def prepare(self) -> PreparedSteeringProposal:
        if self.prepare_error:
            raise self.prepare_error
        return PreparedSteeringProposal(self.proposal)

    def apply(self, prepared: PreparedSteeringProposal) -> SteeringApplyResult:
        if self.apply_error:
            raise self.apply_error
        self.applied = True
        return SteeringApplyResult(
            changed_files=tuple(
                SteeringAppliedFile(change.path, change.action, change.reason)
                for change in prepared.proposal.changes
            )
        )


def steering_proposal() -> SteeringProposal:
    return SteeringProposal(
        summary="Add missing product steering",
        notes=("Only foundational steering files are targeted.",),
        changes=(
            SteeringFileProposal(
                path="steering/product.md",
                action="create",
                reason="Product guidance is missing",
                content="# Product Spec\n\n## Purpose\n- Chat in a terminal.\n",
            ),
        ),
    )


def test_help_describes_the_specode_command() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "specode" in result.stdout


def test_running_without_arguments_shows_the_scaffold_message() -> None:
    result = runner.invoke(app, [], env={"OPENAI_API_KEY": "test-key"})

    assert result.exit_code == 0
    assert "SpeCODE" in result.stdout
    assert "Type / for commands" in result.stdout


def test_exits_with_a_configuration_error_when_openai_api_key_is_missing() -> None:
    result = runner.invoke(app, [], env={"OPENAI_API_KEY": ""})

    assert result.exit_code == 1
    assert "Configuration Error" in result.stdout


def test_renders_an_assistant_reply_for_a_chat_prompt(
    monkeypatch,
) -> None:
    monkeypatch.setattr(cli_module, "create_chat_service", lambda: FakeChatService())

    result = runner.invoke(
        app,
        [],
        env={"OPENAI_API_KEY": "test-key"},
        input="Hello\n/exit\n",
    )

    assert result.exit_code == 0
    assert "> Hello" in result.stdout
    assert "Echo: Hello" in result.stdout
    assert "SpeCODE > Echo: Hello" in result.stdout


def test_clear_resets_the_screen_without_replaying_the_full_welcome(monkeypatch) -> None:
    monkeypatch.setattr(cli_module, "create_chat_service", lambda: FakeChatService())

    result = runner.invoke(
        app,
        [],
        env={"OPENAI_API_KEY": "test-key"},
        input="/clear\n/exit\n",
    )

    assert result.exit_code == 0
    assert (
        result.stdout.count("Terminal-first AI chat that stays compact and keyboard-friendly.") == 1
    )
    assert "Cleared. Type / for commands." in result.stdout


def test_help_command_renders_session_controls(monkeypatch) -> None:
    monkeypatch.setattr(cli_module, "create_chat_service", lambda: FakeChatService())

    result = runner.invoke(
        app,
        [],
        env={"OPENAI_API_KEY": "test-key"},
        input="/help\n/exit\n",
    )

    assert result.exit_code == 0
    assert "Show available session controls" in result.stdout
    assert "/steering" in result.stdout


def test_steering_command_routes_before_normal_chat(monkeypatch) -> None:
    monkeypatch.setattr(cli_module, "create_chat_service", lambda: ErroringChatService())
    workflow = FakeSteeringWorkflow(SteeringProposal())
    monkeypatch.setattr(cli_module, "create_steering_workflow", lambda: workflow)

    result = runner.invoke(
        app,
        [],
        env={"OPENAI_API_KEY": "test-key"},
        input="/steering\n/exit\n",
    )

    assert result.exit_code == 0
    assert "No steering updates needed." in result.stdout
    assert "Temporary failure" not in result.stdout


def test_steering_command_applies_after_explicit_yes(monkeypatch) -> None:
    workflow = FakeSteeringWorkflow(steering_proposal())
    monkeypatch.setattr(cli_module, "create_steering_workflow", lambda: workflow)
    monkeypatch.setattr(cli_module, "create_chat_service", lambda: ErroringChatService())

    result = runner.invoke(
        app,
        [],
        env={"OPENAI_API_KEY": "test-key"},
        input="/steering\ny\n/exit\n",
    )

    assert result.exit_code == 0
    assert "Preparing steering proposal..." in result.stdout
    assert "Steering Proposal" in result.stdout
    assert "steering/product.md" in result.stdout
    assert "Apply these steering changes? [y/N]" in result.stdout
    assert "Steering files changed" in result.stdout
    assert workflow.applied is True
    assert "Temporary failure" not in result.stdout


def test_steering_command_rejects_default_no(monkeypatch) -> None:
    workflow = FakeSteeringWorkflow(steering_proposal())
    monkeypatch.setattr(cli_module, "create_steering_workflow", lambda: workflow)

    result = runner.invoke(
        app,
        [],
        env={"OPENAI_API_KEY": "test-key"},
        input="/steering\n\n/exit\n",
    )

    assert result.exit_code == 0
    assert "No steering files changed" in result.stdout
    assert workflow.applied is False


def test_steering_command_noop_does_not_prompt_for_approval(monkeypatch) -> None:
    workflow = FakeSteeringWorkflow(SteeringProposal(summary="No durable updates"))
    monkeypatch.setattr(cli_module, "create_steering_workflow", lambda: workflow)

    result = runner.invoke(
        app,
        [],
        env={"OPENAI_API_KEY": "test-key"},
        input="/steering\n/exit\n",
    )

    assert result.exit_code == 0
    assert "No steering updates needed." in result.stdout
    assert "Apply these steering changes?" not in result.stdout


def test_steering_prepare_errors_are_recoverable(monkeypatch) -> None:
    workflow = FakeSteeringWorkflow(
        SteeringProposal(),
        prepare_error=SteeringWorkflowError("No safe project evidence was found"),
    )
    monkeypatch.setattr(cli_module, "create_steering_workflow", lambda: workflow)

    result = runner.invoke(
        app,
        [],
        env={"OPENAI_API_KEY": "test-key"},
        input="/steering\n/exit\n",
    )

    assert result.exit_code == 0
    assert "Steering Error" in result.stdout
    assert "No safe project evidence was found" in result.stdout


def test_steering_apply_errors_are_recoverable(monkeypatch) -> None:
    workflow = FakeSteeringWorkflow(
        steering_proposal(),
        apply_error=SteeringValidationError("File changed since preview"),
    )
    monkeypatch.setattr(cli_module, "create_steering_workflow", lambda: workflow)

    result = runner.invoke(
        app,
        [],
        env={"OPENAI_API_KEY": "test-key"},
        input="/steering\ny\n/exit\n",
    )

    assert result.exit_code == 0
    assert "Steering Error" in result.stdout
    assert "File changed since preview" in result.stdout


def test_reply_failures_render_an_inline_error_and_keep_the_session_alive(monkeypatch) -> None:
    monkeypatch.setattr(cli_module, "create_chat_service", lambda: ErroringChatService())

    result = runner.invoke(
        app,
        [],
        env={"OPENAI_API_KEY": "test-key"},
        input="Hello\n/exit\n",
    )

    assert result.exit_code == 0
    assert "Reply Error" in result.stdout
