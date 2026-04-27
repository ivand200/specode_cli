"""Thin Pydantic AI adapter for specode."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import ModelMessage

from specode.config import DEFAULT_MODEL_NAME
from specode.repository import RepositoryError, RepositoryInspector
from specode.steering import (
    SteeringFileProposal,
    SteeringProposal,
    SteeringTextEdit,
)


SPECODE_INSTRUCTIONS = (
    "You are specode, a helpful terminal coding assistant. "
    "Give concise, clear answers that work well in a CLI chat."
)


class ChatServiceError(RuntimeError):
    """Raised when the model cannot return a reply."""


class SteeringDraftServiceError(RuntimeError):
    """Raised when the model cannot draft steering changes."""


@dataclass(frozen=True)
class ChatReply:
    """A normalized chat reply for the session layer."""

    text: str
    new_messages: list[ModelMessage]


class ChatService(Protocol):
    """Stable chat-service boundary for the session workflow."""

    def reply(self, prompt: str, history: list[ModelMessage]) -> ChatReply:
        """Generate one assistant reply for the given prompt."""


class PydanticAIChatService:
    """Chat service backed by a single Pydantic AI agent."""

    def __init__(self, model_name: str = DEFAULT_MODEL_NAME) -> None:
        self._agent = Agent(model_name, instructions=SPECODE_INSTRUCTIONS)

    def reply(self, prompt: str, history: list[ModelMessage]) -> ChatReply:
        """Generate one assistant reply while preserving message history."""
        try:
            result = self._agent.run_sync(prompt, message_history=history)
        except Exception as exc:
            raise ChatServiceError(
                "Couldn't generate a reply. Check your API key, network connection, or model "
                "settings and try again."
            ) from exc

        return ChatReply(text=str(result.output), new_messages=list(result.new_messages()))


class _SteeringTextEditOutput(BaseModel):
    old_text: str = Field(description="Exact existing text to replace")
    new_text: str = Field(description="Replacement text")
    reason: str = Field(default="", description="Why this edit belongs in durable steering")


class _SteeringFileProposalOutput(BaseModel):
    path: str = Field(
        description="Target path, limited to steering/product.md, tech.md, structure.md"
    )
    action: Literal["create", "update", "replace"]
    reason: str = Field(default="", description="Why this file needs a durable steering change")
    content: str = Field(
        default="", description="Full file content for create or replacement actions"
    )
    edits: list[_SteeringTextEditOutput] = Field(
        default_factory=list,
        description="Exact text edits for ordinary updates to existing steering files",
    )


class _SteeringProposalOutput(BaseModel):
    summary: str = Field(default="", description="Compact summary of the steering proposal")
    changes: list[_SteeringFileProposalOutput] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class SteeringDraftService(Protocol):
    """Stable model boundary for project-steering draft generation."""

    def draft(self, repository: RepositoryInspector) -> SteeringProposal:
        """Generate a structured steering proposal from safe repository tools."""


STEERING_DRAFT_INSTRUCTIONS = """You draft tiny durable project steering docs for SpeCode.

Use the read-only repository tools to inspect only enough evidence to identify durable
project-level guidance. Prefer existing steering docs, README files, package manifests,
tool config, entry points, key directories, and representative modules.

Foundational outputs are:
- steering/product.md
- steering/tech.md
- steering/structure.md

Steering fit test:
- Include facts only when they are durable, project-level, useful across multiple tasks,
  and not cheaper to rediscover from code.
- Exclude task requirements, rollout notes, secrets, credentials, sample PII, generated
  config dumps, exhaustive dependency lists, file trees, and drift-prone implementation
  details.

Required shapes:
- product.md: Purpose, Users / Actors, Core Workflows, Core Domain Concepts,
  Scope Boundaries, Durable Constraints.
- tech.md: Stack, Key Services / Infrastructure, Engineering Conventions,
  Related Steering Docs, Technical Constraints.
- structure.md: Repository Shape, Entry Points, Architectural Conventions,
  Module Contract, Where To Put New Work.

For missing or empty foundational files, propose action=create with full compact content.
For ordinary existing files, propose action=update with exact old_text/new_text edits.
Use action=replace only when a non-empty foundational file appears malformed. Keep custom
steering docs read-only; use them only as background when a durable fact clearly belongs
in a foundational file. If no useful durable update is needed, return no changes.
"""

STEERING_DRAFT_PROMPT = (
    "Inspect the current project with the available read-only tools and return a structured "
    "proposal for foundational steering docs. Do not propose task artifacts, source edits, "
    "shell commands, delete operations, or specialized steering docs."
)


class PydanticAISteeringDraftService:
    """Pydantic AI-backed draft service with read-only repository tools."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL_NAME,
        agent: Agent[RepositoryInspector, _SteeringProposalOutput] | None = None,
    ) -> None:
        self._agent = agent or Agent(
            model_name,
            deps_type=RepositoryInspector,
            output_type=_SteeringProposalOutput,
            instructions=STEERING_DRAFT_INSTRUCTIONS,
            tools=(
                _list_files_tool,
                _read_file_tool,
                _search_text_tool,
            ),
        )

    def draft(self, repository: RepositoryInspector) -> SteeringProposal:
        """Draft steering changes, retrying one transient model failure."""
        last_error: Exception | None = None
        for _ in range(2):
            try:
                result = self._agent.run_sync(STEERING_DRAFT_PROMPT, deps=repository)
                return _to_steering_proposal(result.output)
            except RepositoryError as exc:
                raise SteeringDraftServiceError(
                    "Repository inspection failed while drafting steering updates."
                ) from exc
            except Exception as exc:
                last_error = exc

        raise SteeringDraftServiceError(
            "Couldn't draft steering updates. Check your API key, network connection, or model "
            "settings and try again."
        ) from last_error


def _list_files_tool(
    ctx: RunContext[RepositoryInspector], path: str = ".", limit: int = 200
) -> dict[str, object]:
    """List safe repository files under a project-relative path."""
    try:
        listing = ctx.deps.list_files(path=path, limit=limit)
    except RepositoryError as exc:
        return _blocked_tool_result(exc)

    return {
        "ok": True,
        "paths": listing.paths,
        "total_count": listing.total_count,
        "limit": listing.limit,
        "truncated": listing.truncated,
    }


def _read_file_tool(
    ctx: RunContext[RepositoryInspector], path: str, offset: int = 0, limit: int = 200
) -> dict[str, object]:
    """Read a safe text file by 0-based line offset and bounded line count."""
    try:
        read = ctx.deps.read_file(path=path, offset=offset, limit=limit)
    except RepositoryError as exc:
        return _blocked_tool_result(exc)

    return {
        "ok": True,
        "path": read.path,
        "content": read.content,
        "offset": read.offset,
        "limit": read.limit,
        "start_line": read.start_line,
        "end_line": read.end_line,
        "total_lines": read.total_lines,
        "truncated": read.truncated,
        "redacted": read.redacted,
    }


def _search_text_tool(
    ctx: RunContext[RepositoryInspector], query: str, limit: int = 50
) -> dict[str, object]:
    """Search safe repository text and return bounded redacted matching lines."""
    try:
        search = ctx.deps.search_text(query=query, limit=limit)
    except RepositoryError as exc:
        return _blocked_tool_result(exc)

    return {
        "ok": True,
        "query": search.query,
        "matches": [
            {
                "path": match.path,
                "line_number": match.line_number,
                "line": match.line,
                "redacted": match.redacted,
            }
            for match in search.matches
        ],
        "limit": search.limit,
        "truncated": search.truncated,
        "redacted": search.redacted,
    }


def _blocked_tool_result(exc: RepositoryError) -> dict[str, object]:
    return {
        "ok": False,
        "error": str(exc),
        "hint": "Choose a listed safe project-relative text file and continue.",
    }


def _to_steering_proposal(output: _SteeringProposalOutput | SteeringProposal) -> SteeringProposal:
    if isinstance(output, SteeringProposal):
        return output

    return SteeringProposal(
        summary=output.summary,
        notes=tuple(output.notes),
        changes=tuple(
            SteeringFileProposal(
                path=change.path,
                action=change.action,
                reason=change.reason,
                content=change.content,
                edits=tuple(
                    SteeringTextEdit(
                        old_text=edit.old_text,
                        new_text=edit.new_text,
                        reason=edit.reason,
                    )
                    for edit in change.edits
                ),
            )
            for change in output.changes
        ),
    )
