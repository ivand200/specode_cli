from pathlib import Path

import pytest
import specode.steering as steering_module

from specode.steering import (
    PreparedSteeringProposal,
    SteeringFileProposal,
    SteeringProposal,
    SteeringStore,
    SteeringTextEdit,
    SteeringValidationError,
    SteeringWorkflow,
    SteeringWorkflowError,
    is_malformed_foundational_file,
)


PRODUCT_CONTENT = """# Product Spec

## Purpose
- Help developers chat in a terminal.

## Users / Actors
- Developer.

## Core Workflows
- Run the CLI.

## Core Domain Concepts
- Session.

## Scope Boundaries
- No persistence.

## Durable Constraints
- Keep the CLI calm.
"""


class FakeDraftService:
    def __init__(self, proposal: SteeringProposal) -> None:
        self.proposal = proposal
        self.draft_calls = 0

    def draft(self, repository) -> SteeringProposal:
        self.draft_calls += 1
        return self.proposal


def test_creates_missing_foundational_file(tmp_path: Path) -> None:
    store = SteeringStore(tmp_path)
    proposal = SteeringProposal(
        changes=(
            SteeringFileProposal(
                path="steering/product.md",
                action="create",
                content=PRODUCT_CONTENT,
                reason="Add missing product guidance",
            ),
        )
    )

    result = store.apply(proposal)

    assert (tmp_path / "steering/product.md").read_text(encoding="utf-8") == PRODUCT_CONTENT
    assert [changed.path for changed in result.changed_files] == ["steering/product.md"]


def test_treats_empty_foundational_file_as_create_style_content(tmp_path: Path) -> None:
    target = tmp_path / "steering/product.md"
    target.parent.mkdir()
    target.write_text("", encoding="utf-8")
    store = SteeringStore(tmp_path)

    store.apply(
        SteeringProposal(
            changes=(
                SteeringFileProposal(
                    path="steering/product.md",
                    action="create",
                    content=PRODUCT_CONTENT,
                ),
            )
        )
    )

    assert target.read_text(encoding="utf-8") == PRODUCT_CONTENT


def test_updates_existing_file_with_exact_text_edit(tmp_path: Path) -> None:
    target = tmp_path / "steering/product.md"
    target.parent.mkdir()
    target.write_text(PRODUCT_CONTENT, encoding="utf-8")
    store = SteeringStore(tmp_path)

    store.apply(
        SteeringProposal(
            changes=(
                SteeringFileProposal(
                    path="steering/product.md",
                    action="update",
                    edits=(
                        SteeringTextEdit(
                            old_text="- Keep the CLI calm.",
                            new_text="- Keep the CLI calm and readable.",
                        ),
                    ),
                ),
            )
        )
    )

    assert "- Keep the CLI calm and readable." in target.read_text(encoding="utf-8")


def test_rejects_update_when_old_text_is_missing(tmp_path: Path) -> None:
    target = tmp_path / "steering/product.md"
    target.parent.mkdir()
    target.write_text(PRODUCT_CONTENT, encoding="utf-8")
    store = SteeringStore(tmp_path)

    with pytest.raises(SteeringValidationError, match="matched 0 times"):
        store.apply(
            SteeringProposal(
                changes=(
                    SteeringFileProposal(
                        path="steering/product.md",
                        action="update",
                        edits=(SteeringTextEdit(old_text="not here", new_text="replacement"),),
                    ),
                )
            )
        )

    assert target.read_text(encoding="utf-8") == PRODUCT_CONTENT


def test_rejects_ambiguous_update_text(tmp_path: Path) -> None:
    target = tmp_path / "steering/product.md"
    target.parent.mkdir()
    target.write_text("same\nsame\n", encoding="utf-8")
    store = SteeringStore(tmp_path)

    with pytest.raises(SteeringValidationError, match="matched 2 times"):
        store.apply(
            SteeringProposal(
                changes=(
                    SteeringFileProposal(
                        path="steering/product.md",
                        action="update",
                        edits=(SteeringTextEdit(old_text="same", new_text="different"),),
                    ),
                )
            )
        )


def test_rejects_overlapping_edits(tmp_path: Path) -> None:
    target = tmp_path / "steering/product.md"
    target.parent.mkdir()
    target.write_text("abcdef\n", encoding="utf-8")
    store = SteeringStore(tmp_path)

    with pytest.raises(SteeringValidationError, match="Overlapping edits"):
        store.apply(
            SteeringProposal(
                changes=(
                    SteeringFileProposal(
                        path="steering/product.md",
                        action="update",
                        edits=(
                            SteeringTextEdit(old_text="abc", new_text="ABC"),
                            SteeringTextEdit(old_text="bcd", new_text="BCD"),
                        ),
                    ),
                )
            )
        )


def test_replaces_malformed_foundational_file(tmp_path: Path) -> None:
    target = tmp_path / "steering/product.md"
    target.parent.mkdir()
    target.write_text("# Product Spec\n\n## Purpose\n- Too thin.\n", encoding="utf-8")
    store = SteeringStore(tmp_path)

    store.apply(
        SteeringProposal(
            changes=(
                SteeringFileProposal(
                    path="steering/product.md",
                    action="replace",
                    content=PRODUCT_CONTENT,
                ),
            )
        )
    )

    assert target.read_text(encoding="utf-8") == PRODUCT_CONTENT


def test_rejects_replace_for_well_formed_foundational_file(tmp_path: Path) -> None:
    target = tmp_path / "steering/product.md"
    target.parent.mkdir()
    target.write_text(PRODUCT_CONTENT, encoding="utf-8")
    store = SteeringStore(tmp_path)

    with pytest.raises(SteeringValidationError, match="only allowed for malformed"):
        store.apply(
            SteeringProposal(
                changes=(
                    SteeringFileProposal(
                        path="steering/product.md",
                        action="replace",
                        content=PRODUCT_CONTENT.replace("terminal", "shell"),
                    ),
                )
            )
        )

    assert target.read_text(encoding="utf-8") == PRODUCT_CONTENT


@pytest.mark.parametrize(
    "path",
    [
        "README.md",
        "steering/vision.md",
        "tasks/example/task.md",
        "src/specode/session.py",
        "../steering/product.md",
    ],
)
def test_rejects_writes_outside_foundational_steering_files(tmp_path: Path, path: str) -> None:
    store = SteeringStore(tmp_path)

    with pytest.raises(SteeringValidationError):
        store.apply(
            SteeringProposal(
                changes=(SteeringFileProposal(path=path, action="create", content=PRODUCT_CONTENT),)
            )
        )

    assert not (tmp_path / "README.md").exists()
    assert not (tmp_path / "steering/vision.md").exists()
    assert not (tmp_path / "tasks").exists()


@pytest.mark.parametrize(
    "content",
    [
        "OPENAI_API_KEY=sk-test\n",
        "openai_api_key=sk-test\n",
        "api_token: secret-value\n",
        "Authorization: Bearer abcdefghijklmnop\n",
    ],
)
def test_rejects_secret_looking_content(tmp_path: Path, content: str) -> None:
    store = SteeringStore(tmp_path)

    with pytest.raises(SteeringValidationError, match="secret-looking"):
        store.apply(
            SteeringProposal(
                changes=(
                    SteeringFileProposal(
                        path="steering/product.md",
                        action="create",
                        content=content,
                    ),
                )
            )
        )


def test_stages_all_changes_before_writing_anything(tmp_path: Path) -> None:
    store = SteeringStore(tmp_path)

    with pytest.raises(SteeringValidationError):
        store.apply(
            SteeringProposal(
                changes=(
                    SteeringFileProposal(
                        path="steering/product.md",
                        action="create",
                        content=PRODUCT_CONTENT,
                    ),
                    SteeringFileProposal(
                        path="src/specode/session.py",
                        action="create",
                        content="bad",
                    ),
                )
            )
        )

    assert not (tmp_path / "steering/product.md").exists()


def test_rolls_back_if_a_later_write_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = SteeringStore(tmp_path)
    proposal = SteeringProposal(
        changes=(
            SteeringFileProposal(
                path="steering/product.md",
                action="create",
                content=PRODUCT_CONTENT,
            ),
            SteeringFileProposal(
                path="steering/tech.md",
                action="create",
                content="# Tech Spec\n\n## Stack\n- Python\n",
            ),
        )
    )
    original_replace = steering_module.os.replace
    replace_calls = 0

    def fail_second_replace(src: Path, dst: Path) -> None:
        nonlocal replace_calls
        replace_calls += 1
        if replace_calls == 2:
            raise OSError("disk write failed")
        original_replace(src, dst)

    monkeypatch.setattr(steering_module.os, "replace", fail_second_replace)

    with pytest.raises(OSError, match="disk write failed"):
        store.apply(proposal)

    assert not (tmp_path / "steering/product.md").exists()
    assert not (tmp_path / "steering/tech.md").exists()


def test_preserves_crlf_line_endings_for_updates(tmp_path: Path) -> None:
    target = tmp_path / "steering/product.md"
    target.parent.mkdir()
    target.write_bytes(PRODUCT_CONTENT.replace("\n", "\r\n").encode("utf-8"))
    store = SteeringStore(tmp_path)

    store.apply(
        SteeringProposal(
            changes=(
                SteeringFileProposal(
                    path="steering/product.md",
                    action="update",
                    edits=(
                        SteeringTextEdit(
                            old_text="- Keep the CLI calm.",
                            new_text="- Keep the CLI calm and readable.",
                        ),
                    ),
                ),
            )
        )
    )

    content = target.read_bytes()
    assert b"\r\n" in content
    assert b"\n## Durable Constraints\r\n" in content
    assert b"- Keep the CLI calm and readable.\r\n" in content


def test_detects_malformed_foundational_docs_by_expected_headings() -> None:
    assert is_malformed_foundational_file("steering/product.md", "# Product Spec\n## Purpose\n")
    assert not is_malformed_foundational_file("steering/product.md", PRODUCT_CONTENT)


def test_workflow_prepares_and_applies_validated_proposal(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    proposal = SteeringProposal(
        changes=(
            SteeringFileProposal(
                path="steering/product.md",
                action="create",
                content=PRODUCT_CONTENT,
            ),
        )
    )
    draft_service = FakeDraftService(proposal)
    workflow = SteeringWorkflow(tmp_path, draft_service=draft_service)

    prepared = workflow.prepare()
    result = workflow.apply(prepared)

    assert isinstance(prepared, PreparedSteeringProposal)
    assert draft_service.draft_calls == 1
    assert [changed.path for changed in result.changed_files] == ["steering/product.md"]
    assert (tmp_path / "steering/product.md").read_text(encoding="utf-8") == PRODUCT_CONTENT


def test_workflow_refuses_directories_without_safe_project_evidence(tmp_path: Path) -> None:
    workflow = SteeringWorkflow(tmp_path, draft_service=FakeDraftService(SteeringProposal()))

    with pytest.raises(SteeringWorkflowError, match="No safe project evidence"):
        workflow.prepare()
