"""Thin Pydantic AI adapter for specode."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import ModelMessage
from pydantic_ai.settings import ModelSettings

from specode.config import DEFAULT_MODEL_NAME, DEFAULT_MODEL_SETTINGS
from specode.repository import RepositoryError, RepositoryInspector
from specode.steering import (
    SteeringDraftService,
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

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL_NAME,
        model_settings: ModelSettings | None = None,
    ) -> None:
        self._agent = Agent(
            model_name,
            instructions=SPECODE_INSTRUCTIONS,
            model_settings=model_settings or DEFAULT_MODEL_SETTINGS.copy(),
        )

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
        description=(
            "Target path, limited to steering/product.md, steering/tech.md, "
            "or steering/structure.md"
        )
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


STEERING_DRAFT_INSTRUCTIONS = """You maintain tiny, durable project-level steering docs for SpeCode.

Steering docs are not task plans, code inventories, or generated project summaries.
They capture stable facts that future AI coding sessions should not have to rediscover.

Use steering/ by default and write only foundational steering docs:
- steering/product.md
- steering/tech.md
- steering/structure.md

Refresh existing files in place with targeted edits. Do not create parallel copies.
Add a focused steering doc only when repeated specialized guidance no longer fits cleanly
in a few bullets, but keep custom steering docs read-only in this workflow.

Inspect evidence in this order:
1. existing steering/
2. README*
3. package manifests and tool config
4. top-level files and directories
5. entry points
6. representative source and tests
7. optional task files, only for durable facts or steering gaps

Prefer current repository evidence and explicit user direction over older docs.

Include facts only when they are:
- durable
- project-level
- useful across multiple tasks
- supported by repo evidence or explicit user direction
- not cheaper to rediscover from code

Exclude:
- task-specific requirements, acceptance criteria, or implementation plans
- changelogs or temporary rollout notes
- secrets, credentials, sample PII
- generated config dumps, dependency dumps, or file inventories
- speculative architecture or implementation details likely to drift

Required shapes:
- product.md: Purpose, Users / Actors, Core Workflows, Core Domain Concepts,
  Scope Boundaries, Durable Constraints.
- tech.md: Stack, Key Services / Infrastructure, Engineering Conventions,
  Related Steering Docs, Technical Constraints.
- structure.md: Repository Shape, Entry Points, Architectural Conventions,
  Module Contract, Module Interface Map when stable module boundaries are known and the map
  will prevent repeated rediscovery or boundary violations, Where To Put New Work.

Keep structure.md sections distinct:
- Entry Points answers where execution or reading starts.
- Where To Put New Work answers where a change should live.
- Module Contract answers what broad rules changes must respect.
- Module Interface Map answers what stable boundaries, contracts, and hidden details
  future work must respect.

Module Contract and Module Interface Map should stay compact. The map is a boundary map,
not a file inventory. Include only durable boundaries where the map teaches something
not cheaper to rediscover from code: ownership, invariants, allowed dependencies,
hidden design decisions, review risk, or test boundary.

For each mapped boundary, prefer one compact bullet or row that captures:
- module or subsystem name
- responsibility or design decision it owns
- public interface callers may rely on, such as endpoints, commands, events, schemas,
  services, or exported operations
- implementation details callers and tests must not depend on, such as storage layout,
  helper call order, prompts, retry mechanics, cache behavior, log text, private state,
  or algorithm choice
- contract or behavior tests that protect the boundary, when known
- changes that require deeper review, such as public contract, auth, permissions,
  data integrity, migration, concurrency, performance, operational risk, or boundary leakage

Do not use Module Interface Map for:
- listing files and their obvious contents
- repeating Entry Points or Where To Put New Work
- documenting private helpers, call graphs, or implementation sequence
- speculative future modules
- task-specific design notes
- every folder in the repo

Prefer short bullets. Capture the "why" behind important conventions when evidence supports it.
For missing or empty files, propose action=create with full compact content.
For existing files, propose action=update with exact old_text/new_text edits.
Use action=replace only for malformed non-empty foundational files.

Before returning, check that each proposed change is concise, evidence-backed,
in the right file, and useful enough that future agents should not rediscover it.
Return no changes if the current steering docs are already good enough.
Update steering only when durable truth changed. Task scale is irrelevant: do not refresh
steering just because a task is large, and do not skip relevant steering just because a task
is small.
"""

STEERING_DRAFT_PROMPT = (
    "Inspect the current project with read-only tools. Draft only necessary foundational "
    "steering changes. Prefer no changes over noisy or speculative docs."
)


class PydanticAISteeringDraftService(SteeringDraftService):
    """Pydantic AI-backed draft service with read-only repository tools."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL_NAME,
        model_settings: ModelSettings | None = None,
        agent: Agent[RepositoryInspector, _SteeringProposalOutput] | None = None,
    ) -> None:
        self._agent = agent or Agent(
            model_name,
            deps_type=RepositoryInspector,
            output_type=_SteeringProposalOutput,
            instructions=STEERING_DRAFT_INSTRUCTIONS,
            model_settings=model_settings or DEFAULT_MODEL_SETTINGS.copy(),
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
