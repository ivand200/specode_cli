"""Steering proposal validation and approval-gated writes."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path, PurePosixPath
import re
from typing import Literal, Protocol

from specode.repository import RepositoryInspector


SteeringAction = Literal["create", "update", "replace"]

FOUNDATIONAL_STEERING_FILES = frozenset(
    {
        "steering/product.md",
        "steering/tech.md",
        "steering/structure.md",
    }
)

EXPECTED_HEADINGS = {
    "steering/product.md": (
        "Purpose",
        "Users / Actors",
        "Core Workflows",
        "Core Domain Concepts",
        "Scope Boundaries",
        "Durable Constraints",
    ),
    "steering/tech.md": (
        "Stack",
        "Key Services / Infrastructure",
        "Engineering Conventions",
        "Related Steering Docs",
        "Technical Constraints",
    ),
    "steering/structure.md": (
        "Repository Shape",
        "Entry Points",
        "Architectural Conventions",
        "Module Contract",
        "Where To Put New Work",
    ),
}

SECRET_CONTENT_PATTERN = re.compile(
    r"(?im)^\s*[A-Z0-9_]*(?:API[_-]?KEY|TOKEN|SECRET|PASSWORD)[A-Z0-9_]*\s*[:=]\s*\S+"
)

GENERATED_DUMP_MARKERS = (
    "-----BEGIN PRIVATE KEY-----",
    "-----BEGIN RSA PRIVATE KEY-----",
    "-----BEGIN OPENSSH PRIVATE KEY-----",
)


class SteeringValidationError(ValueError):
    """Raised when a steering proposal is unsafe or cannot be applied exactly."""


class SteeringWorkflowError(RuntimeError):
    """Raised when the steering workflow cannot safely continue."""


class SteeringDraftService(Protocol):
    """Stable model boundary for project-steering draft generation."""

    def draft(self, repository: RepositoryInspector) -> "SteeringProposal":
        """Generate a structured steering proposal from safe repository tools."""


@dataclass(frozen=True)
class SteeringTextEdit:
    """One exact text replacement for an existing steering file."""

    old_text: str
    new_text: str
    reason: str = ""


@dataclass(frozen=True)
class SteeringFileProposal:
    """A proposed create, update, or replacement for one steering file."""

    path: str
    action: SteeringAction
    reason: str = ""
    content: str = ""
    edits: tuple[SteeringTextEdit, ...] = ()


@dataclass(frozen=True)
class SteeringProposal:
    """A model- or test-created proposal for steering changes."""

    summary: str = ""
    changes: tuple[SteeringFileProposal, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class SteeringAppliedFile:
    """One steering file changed by an approved proposal."""

    path: str
    action: SteeringAction
    reason: str = ""


@dataclass(frozen=True)
class SteeringApplyResult:
    """Result of applying approved steering changes."""

    changed_files: tuple[SteeringAppliedFile, ...] = ()


@dataclass(frozen=True)
class PreparedSteeringProposal:
    """A validated steering proposal ready for preview and approval."""

    proposal: SteeringProposal


@dataclass(frozen=True)
class _StagedChange:
    path: str
    absolute_path: Path
    action: SteeringAction
    final_content: str
    reason: str = ""
    original_bytes: bytes | None = None


@dataclass(frozen=True)
class _StagedProposal:
    changes: tuple[_StagedChange, ...] = field(default_factory=tuple)


class SteeringStore:
    """Validate and apply approved changes to foundational steering docs only."""

    def __init__(self, project_root: Path | str) -> None:
        self.project_root = Path(project_root).resolve()

    def validate_proposal(self, proposal: SteeringProposal) -> None:
        """Validate a proposal without writing any files."""
        self._stage(proposal)

    def apply(self, proposal: SteeringProposal) -> SteeringApplyResult:
        """Apply an approved proposal, writing nothing unless every change stages cleanly."""
        staged = self._stage(proposal)

        self._write_staged_changes(staged.changes)

        return SteeringApplyResult(
            changed_files=tuple(
                SteeringAppliedFile(change.path, change.action, change.reason)
                for change in staged.changes
            )
        )

    @staticmethod
    def _write_staged_changes(changes: tuple[_StagedChange, ...]) -> None:
        temp_paths: list[Path] = []
        committed: list[_StagedChange] = []

        try:
            for index, change in enumerate(changes):
                change.absolute_path.parent.mkdir(parents=True, exist_ok=True)
                temp_path = change.absolute_path.with_name(
                    f".{change.absolute_path.name}.specode-{os.getpid()}-{index}.tmp"
                )
                with temp_path.open("w", encoding="utf-8", newline="") as handle:
                    handle.write(change.final_content)
                temp_paths.append(temp_path)

            for change, temp_path in zip(changes, temp_paths):
                os.replace(temp_path, change.absolute_path)
                committed.append(change)
        except Exception:
            for change in reversed(committed):
                if change.original_bytes is None:
                    change.absolute_path.unlink(missing_ok=True)
                else:
                    change.absolute_path.write_bytes(change.original_bytes)
            for temp_path in temp_paths:
                temp_path.unlink(missing_ok=True)
            raise

    def _stage(self, proposal: SteeringProposal) -> _StagedProposal:
        staged: list[_StagedChange] = []
        seen_paths: set[str] = set()

        for change in proposal.changes:
            relative_path = _normalize_steering_path(change.path)
            if relative_path in seen_paths:
                raise SteeringValidationError(f"Duplicate proposal for {relative_path}.")
            seen_paths.add(relative_path)

            absolute_path = self.project_root / relative_path
            current_content = _read_text_if_present(absolute_path)
            if change.action == "create":
                final_content = self._stage_create(change, current_content)
            elif change.action == "update":
                final_content = self._stage_update(change, current_content)
            elif change.action == "replace":
                final_content = self._stage_replace(relative_path, change, current_content)
            else:
                raise SteeringValidationError(f"Unsupported steering action: {change.action}.")

            _validate_safe_content(final_content)
            line_ending = _line_ending_for(current_content)
            staged.append(
                _StagedChange(
                    path=relative_path,
                    absolute_path=absolute_path,
                    action=change.action,
                    final_content=_prepare_final_content(final_content, line_ending),
                    reason=change.reason,
                    original_bytes=_read_bytes_if_present(absolute_path),
                )
            )

        return _StagedProposal(changes=tuple(staged))

    @staticmethod
    def _stage_create(change: SteeringFileProposal, current_content: str | None) -> str:
        if not change.content.strip():
            raise SteeringValidationError("Create proposals must include non-empty content.")
        if current_content is not None and current_content.strip():
            raise SteeringValidationError(f"Cannot create over existing file {change.path}.")
        if change.edits:
            raise SteeringValidationError("Create proposals cannot include text edits.")
        return change.content

    @staticmethod
    def _stage_update(change: SteeringFileProposal, current_content: str | None) -> str:
        if current_content is None or not current_content.strip():
            raise SteeringValidationError(f"Cannot update missing or empty file {change.path}.")
        if change.content.strip():
            raise SteeringValidationError("Update proposals must use edits, not full content.")
        if not change.edits:
            raise SteeringValidationError("Update proposals must include at least one edit.")

        ranges: list[tuple[int, int]] = []
        for edit in change.edits:
            if not edit.old_text:
                raise SteeringValidationError("Update edits must include non-empty old_text.")
            count = current_content.count(edit.old_text)
            if count != 1:
                raise SteeringValidationError(
                    f"Edit for {change.path} must match exactly once; matched {count} times."
                )
            start = current_content.index(edit.old_text)
            ranges.append((start, start + len(edit.old_text)))

        sorted_ranges = sorted(ranges)
        for previous, current in zip(sorted_ranges, sorted_ranges[1:]):
            if current[0] < previous[1]:
                raise SteeringValidationError(
                    f"Overlapping edits are not allowed for {change.path}."
                )

        final_content = current_content
        for edit in change.edits:
            final_content = final_content.replace(edit.old_text, edit.new_text, 1)

        return final_content

    @staticmethod
    def _stage_replace(
        relative_path: str, change: SteeringFileProposal, current_content: str | None
    ) -> str:
        if not change.content.strip():
            raise SteeringValidationError("Replace proposals must include non-empty content.")
        if current_content is None or not current_content.strip():
            raise SteeringValidationError(
                "Missing or empty steering files must be handled with create proposals."
            )
        if change.edits:
            raise SteeringValidationError("Replace proposals cannot include text edits.")
        if not is_malformed_foundational_file(relative_path, current_content):
            raise SteeringValidationError(
                f"Full replacement is only allowed for malformed foundational docs: {change.path}."
            )
        return change.content


class SteeringWorkflow:
    """Coordinate safe repository research, draft validation, and approved writes."""

    def __init__(
        self,
        project_root: Path | str,
        draft_service: SteeringDraftService,
        repository: RepositoryInspector | None = None,
        store: SteeringStore | None = None,
    ) -> None:
        self.project_root = Path(project_root)
        self.repository = repository or RepositoryInspector(self.project_root)
        self.store = store or SteeringStore(self.project_root)
        self.draft_service = draft_service

    def prepare(self) -> PreparedSteeringProposal:
        """Inspect, draft, and validate a steering proposal without writing files."""
        listing = self.repository.list_files(limit=1)
        if not listing.paths:
            raise SteeringWorkflowError("No safe project evidence was found in this directory.")

        proposal = self.draft_service.draft(self.repository)
        self.store.validate_proposal(proposal)
        return PreparedSteeringProposal(proposal=proposal)

    def apply(self, prepared: PreparedSteeringProposal) -> SteeringApplyResult:
        """Apply a previously validated proposal after explicit user approval."""
        return self.store.apply(prepared.proposal)


def is_malformed_foundational_file(relative_path: str, content: str) -> bool:
    """Return true when a non-empty foundational doc has too few expected headings."""
    expected = EXPECTED_HEADINGS[_normalize_steering_path(relative_path)]
    found = 0
    for heading in expected:
        pattern = re.compile(rf"(?m)^##\s+{re.escape(heading)}\s*$")
        if pattern.search(content):
            found += 1
    return found < 3


def _normalize_steering_path(path: str) -> str:
    raw = PurePosixPath(path.replace("\\", "/"))
    parts = raw.parts
    if raw.is_absolute() or ".." in parts:
        raise SteeringValidationError(f"Unsupported steering path: {path}.")
    if parts and parts[0] == ".":
        raw = PurePosixPath(*parts[1:])

    normalized = raw.as_posix()
    if normalized not in FOUNDATIONAL_STEERING_FILES:
        raise SteeringValidationError(
            f"Steering writes are limited to foundational docs, got {path}."
        )
    return normalized


def _read_text_if_present(path: Path) -> str | None:
    if not path.exists():
        return None
    if not path.is_file():
        raise SteeringValidationError(f"Steering target is not a file: {path}.")
    return path.read_bytes().decode("utf-8")


def _read_bytes_if_present(path: Path) -> bytes | None:
    if not path.exists():
        return None
    if not path.is_file():
        raise SteeringValidationError(f"Steering target is not a file: {path}.")
    return path.read_bytes()


def _validate_safe_content(content: str) -> None:
    if SECRET_CONTENT_PATTERN.search(content):
        raise SteeringValidationError("Steering content appears to contain secret-looking values.")
    if any(marker in content for marker in GENERATED_DUMP_MARKERS):
        raise SteeringValidationError("Steering content appears to contain generated secret dumps.")


def _line_ending_for(current_content: str | None) -> str:
    if current_content and "\r\n" in current_content:
        return "\r\n"
    return "\n"


def _prepare_final_content(content: str, line_ending: str) -> str:
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.endswith("\n"):
        normalized = f"{normalized}\n"
    if line_ending == "\n":
        return normalized
    return normalized.replace("\n", line_ending)
