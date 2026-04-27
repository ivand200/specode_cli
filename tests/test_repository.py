from pathlib import Path

import pytest

from specode.repository import (
    RepositoryFileRejected,
    RepositoryInspector,
    UnsafeWorkspaceError,
    WorkspacePolicy,
)


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_list_files_returns_sorted_capped_safe_paths(tmp_path: Path) -> None:
    write_file(tmp_path / "zeta.py", "print('z')\n")
    write_file(tmp_path / "alpha.py", "print('a')\n")
    write_file(tmp_path / "docs" / "beta.md", "Beta\n")
    write_file(tmp_path / "image.png", "not listed even when text-shaped\n")

    listing = RepositoryInspector(tmp_path).list_files(limit=2)

    assert listing.paths == ["alpha.py", "docs/beta.md"]
    assert listing.total_count == 3
    assert listing.truncated is True


def test_read_file_returns_paged_content_and_metadata(tmp_path: Path) -> None:
    write_file(tmp_path / "notes.md", "one\ntwo\nthree\nfour\nfive\n")

    result = RepositoryInspector(tmp_path).read_file("notes.md", offset=1, limit=2)

    assert result.content == "two\nthree\n"
    assert result.path == "notes.md"
    assert result.offset == 1
    assert result.limit == 2
    assert result.start_line == 2
    assert result.end_line == 3
    assert result.total_lines == 5
    assert result.truncated is True
    assert result.redacted is False


def test_search_text_returns_bounded_sorted_matches(tmp_path: Path) -> None:
    write_file(tmp_path / "c.md", "needle in c\n")
    write_file(tmp_path / "a.md", "needle in a\n")
    write_file(tmp_path / "b.md", "needle in b\n")

    result = RepositoryInspector(tmp_path).search_text("needle", limit=2)

    assert [(match.path, match.line_number, match.line) for match in result.matches] == [
        ("a.md", 1, "needle in a"),
        ("b.md", 1, "needle in b"),
    ]
    assert result.truncated is True


def test_all_safe_steering_markdown_files_are_readable(tmp_path: Path) -> None:
    write_file(tmp_path / "steering" / "product.md", "# Product\n")
    write_file(tmp_path / "steering" / "vision.md", "# Vision\nCustom durable guidance\n")

    inspector = RepositoryInspector(tmp_path)

    assert inspector.list_files("steering").paths == [
        "steering/product.md",
        "steering/vision.md",
    ]
    assert (
        inspector.read_file("steering/vision.md").content == "# Vision\nCustom durable guidance\n"
    )


def test_policy_refuses_obvious_unsafe_roots() -> None:
    with pytest.raises(UnsafeWorkspaceError):
        WorkspacePolicy(Path.home())

    with pytest.raises(UnsafeWorkspaceError):
        WorkspacePolicy(Path("/"))


def test_list_files_excludes_lockfiles_dependencies_caches_and_generated_noise(
    tmp_path: Path,
) -> None:
    write_file(tmp_path / "src" / "app.py", "print('safe')\n")
    write_file(tmp_path / "uv.lock", "giant lock dump\n")
    write_file(tmp_path / "package-lock.json", "{}\n")
    write_file(tmp_path / "node_modules" / "pkg" / "index.js", "ignored\n")
    write_file(tmp_path / ".venv" / "pyvenv.cfg", "ignored\n")
    write_file(tmp_path / "__pycache__" / "app.pyc", "ignored\n")
    write_file(tmp_path / ".pytest_cache" / "README.md", "ignored\n")
    write_file(tmp_path / "dist" / "bundle.js", "ignored\n")
    write_file(tmp_path / "coverage" / "index.html", "ignored\n")

    listing = RepositoryInspector(tmp_path).list_files()

    assert listing.paths == ["src/app.py"]


def test_env_files_are_blocked_but_safe_templates_are_allowed(tmp_path: Path) -> None:
    write_file(tmp_path / ".env", "API_TOKEN=real\n")
    write_file(tmp_path / ".env.local", "API_TOKEN=local\n")
    write_file(tmp_path / ".env.example", "API_TOKEN=example\n")
    write_file(tmp_path / ".env.template", "API_TOKEN=template\n")

    inspector = RepositoryInspector(tmp_path)

    assert inspector.list_files().paths == [".env.example", ".env.template"]
    with pytest.raises(RepositoryFileRejected):
        inspector.read_file(".env")
    with pytest.raises(RepositoryFileRejected):
        inspector.read_file(".env.local")


def test_read_file_refuses_binary_and_large_files(tmp_path: Path) -> None:
    binary = tmp_path / "binary.txt"
    binary.write_bytes(b"hello\x00world")
    write_file(tmp_path / "too-large.md", "01234567890\n")
    policy = WorkspacePolicy(tmp_path, max_file_bytes=10)
    inspector = RepositoryInspector(tmp_path, policy=policy)

    with pytest.raises(RepositoryFileRejected):
        inspector.read_file("binary.txt")
    with pytest.raises(RepositoryFileRejected):
        inspector.read_file("too-large.md")


def test_read_file_redacts_secret_looking_values(tmp_path: Path) -> None:
    write_file(
        tmp_path / "settings.py",
        'API_TOKEN = "supersecret"\nAUTH_HEADER = "Bearer abcdefghijklmnop"\n',
    )

    result = RepositoryInspector(tmp_path).read_file("settings.py")

    assert "supersecret" not in result.content
    assert "abcdefghijklmnop" not in result.content
    assert 'API_TOKEN = "[REDACTED]"' in result.content
    assert 'AUTH_HEADER = "[REDACTED]"' in result.content
    assert result.redacted is True


def test_search_text_redacts_secret_looking_values(tmp_path: Path) -> None:
    write_file(tmp_path / "settings.py", "API_TOKEN=supersecret\nnormal=visible\n")

    result = RepositoryInspector(tmp_path).search_text("supersecret")

    assert len(result.matches) == 1
    assert result.matches[0].line == "API_TOKEN=[REDACTED]"
    assert result.matches[0].redacted is True
    assert result.redacted is True
