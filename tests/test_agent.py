from pathlib import Path

import pytest

from specode.agent import (
    PydanticAISteeringDraftService,
    STEERING_DRAFT_PROMPT,
    SteeringDraftServiceError,
    _list_files_tool,
    _read_file_tool,
    _search_text_tool,
)
from specode.repository import RepositoryError, RepositoryInspector
from specode.steering import SteeringFileProposal, SteeringProposal


class FakeRunResult:
    def __init__(self, output: SteeringProposal) -> None:
        self.output = output


class FakeAgent:
    def __init__(self, outputs: list[SteeringProposal], failures: int = 0) -> None:
        self.outputs = outputs
        self.failures = failures
        self.calls: list[tuple[str, RepositoryInspector]] = []

    def run_sync(self, prompt: str, *, deps: RepositoryInspector) -> FakeRunResult:
        self.calls.append((prompt, deps))
        if self.failures:
            self.failures -= 1
            raise RuntimeError("temporary model failure")
        return FakeRunResult(self.outputs.pop(0))


class RepositoryErrorAgent:
    def __init__(self) -> None:
        self.calls = 0

    def run_sync(self, prompt: str, *, deps: RepositoryInspector) -> FakeRunResult:
        self.calls += 1
        raise RepositoryError("unsafe path")


class ToolContext:
    def __init__(self, deps: RepositoryInspector) -> None:
        self.deps = deps


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_steering_draft_service_returns_structured_proposal(tmp_path: Path) -> None:
    repository = RepositoryInspector(tmp_path)
    proposal = SteeringProposal(
        summary="Add product steering",
        changes=(
            SteeringFileProposal(
                path="steering/product.md",
                action="create",
                content="# Product Spec\n",
            ),
        ),
    )
    fake_agent = FakeAgent([proposal])
    service = PydanticAISteeringDraftService(agent=fake_agent)

    result = service.draft(repository)

    assert result == proposal
    assert fake_agent.calls == [(STEERING_DRAFT_PROMPT, repository)]


def test_steering_draft_service_retries_one_transient_failure(tmp_path: Path) -> None:
    repository = RepositoryInspector(tmp_path)
    proposal = SteeringProposal(summary="No changes")
    fake_agent = FakeAgent([proposal], failures=1)
    service = PydanticAISteeringDraftService(agent=fake_agent)

    result = service.draft(repository)

    assert result == proposal
    assert len(fake_agent.calls) == 2


def test_steering_draft_service_raises_after_retry_failure(tmp_path: Path) -> None:
    repository = RepositoryInspector(tmp_path)
    fake_agent = FakeAgent([], failures=2)
    service = PydanticAISteeringDraftService(agent=fake_agent)

    with pytest.raises(SteeringDraftServiceError):
        service.draft(repository)

    assert len(fake_agent.calls) == 2


def test_steering_draft_service_does_not_retry_repository_errors(tmp_path: Path) -> None:
    repository = RepositoryInspector(tmp_path)
    fake_agent = RepositoryErrorAgent()
    service = PydanticAISteeringDraftService(agent=fake_agent)

    with pytest.raises(SteeringDraftServiceError, match="Repository inspection failed"):
        service.draft(repository)

    assert fake_agent.calls == 1


def test_steering_repository_tools_expose_safe_bounded_results(tmp_path: Path) -> None:
    write_file(tmp_path / "README.md", "API_TOKEN=secret\nneedle\n")
    write_file(tmp_path / ".env", "API_TOKEN=real\n")
    ctx = ToolContext(RepositoryInspector(tmp_path))

    listing = _list_files_tool(ctx, limit=10)
    read = _read_file_tool(ctx, path="README.md", limit=1)
    search = _search_text_tool(ctx, query="secret")

    assert listing["ok"] is True
    assert listing["paths"] == ["README.md"]
    assert read["ok"] is True
    assert read["content"] == "API_TOKEN=[REDACTED]\n"
    assert read["redacted"] is True
    assert search["ok"] is True
    assert search["matches"] == [
        {
            "path": "README.md",
            "line_number": 1,
            "line": "API_TOKEN=[REDACTED]",
            "redacted": True,
        }
    ]


def test_steering_repository_tools_return_blocked_results_for_policy_refusals(
    tmp_path: Path,
) -> None:
    write_file(tmp_path / ".env", "API_TOKEN=real\n")
    ctx = ToolContext(RepositoryInspector(tmp_path))

    read = _read_file_tool(ctx, path=".env")
    listing = _list_files_tool(ctx, path="../outside")
    search = _search_text_tool(ctx, query="")

    assert read["ok"] is False
    assert "excluded by workspace policy" in str(read["error"])
    assert listing["ok"] is False
    assert "outside the project root" in str(listing["error"])
    assert search["ok"] is False
    assert "query must not be empty" in str(search["error"])
