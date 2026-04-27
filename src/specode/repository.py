"""Safe repository inspection for model-visible project research."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


MAX_MODEL_VISIBLE_FILE_BYTES = 1_000_000


class RepositoryError(ValueError):
    """Raised when repository inspection refuses a path or operation."""


class UnsafeWorkspaceError(RepositoryError):
    """Raised when a workspace root is too broad to inspect safely."""


class UnsafePathError(RepositoryError):
    """Raised when a requested path escapes the workspace root."""


class RepositoryFileRejected(RepositoryError):
    """Raised when a file is excluded from model-visible inspection."""


@dataclass(frozen=True)
class FileListing:
    """Bounded list of safe repository-relative file paths."""

    paths: list[str]
    total_count: int
    limit: int
    truncated: bool


@dataclass(frozen=True)
class FileRead:
    """Paged model-visible file content with useful read metadata."""

    path: str
    content: str
    offset: int
    limit: int
    start_line: int
    end_line: int
    total_lines: int
    truncated: bool
    redacted: bool


@dataclass(frozen=True)
class TextSearchMatch:
    """One redacted text search match."""

    path: str
    line_number: int
    line: str
    redacted: bool


@dataclass(frozen=True)
class TextSearch:
    """Bounded search results across safe repository files."""

    query: str
    matches: list[TextSearchMatch]
    limit: int
    truncated: bool
    redacted: bool


@dataclass(frozen=True)
class RedactedText:
    """Text plus whether any secret-looking value was removed."""

    text: str
    redacted: bool


@dataclass(frozen=True)
class WorkspacePolicy:
    """Built-in read policy for a single explicit project root."""

    project_root: Path
    max_file_bytes: int = MAX_MODEL_VISIBLE_FILE_BYTES

    ignored_dir_names: frozenset[str] = frozenset(
        {
            ".cache",
            ".eggs",
            ".git",
            ".hg",
            ".idea",
            ".mypy_cache",
            ".next",
            ".nox",
            ".nuxt",
            ".parcel-cache",
            ".pytest_cache",
            ".ruff_cache",
            ".svn",
            ".svelte-kit",
            ".tox",
            ".turbo",
            ".venv",
            ".vscode",
            "__pycache__",
            "bower_components",
            "build",
            "coverage",
            "dist",
            "env",
            "generated",
            "htmlcov",
            "node_modules",
            "out",
            "target",
            "venv",
        }
    )
    ignored_file_names: frozenset[str] = frozenset(
        {
            ".coverage",
            ".DS_Store",
            "bun.lock",
            "Cargo.lock",
            "composer.lock",
            "Gemfile.lock",
            "go.sum",
            "package-lock.json",
            "Pipfile.lock",
            "pnpm-lock.yaml",
            "poetry.lock",
            "uv.lock",
            "yarn.lock",
        }
    )
    ignored_suffixes: frozenset[str] = frozenset(
        {
            ".7z",
            ".avi",
            ".bin",
            ".bmp",
            ".bz2",
            ".class",
            ".db",
            ".dll",
            ".dylib",
            ".egg-info",
            ".exe",
            ".flac",
            ".gif",
            ".gz",
            ".ico",
            ".jar",
            ".jpeg",
            ".jpg",
            ".mkv",
            ".mov",
            ".mp3",
            ".mp4",
            ".npy",
            ".otf",
            ".parquet",
            ".pdf",
            ".pkl",
            ".png",
            ".pyc",
            ".pyo",
            ".rar",
            ".so",
            ".sqlite",
            ".svg",
            ".tar",
            ".tgz",
            ".ttf",
            ".wasm",
            ".wav",
            ".webp",
            ".woff",
            ".woff2",
            ".xz",
            ".zip",
        }
    )
    allowed_env_templates: frozenset[str] = frozenset({".env.example", ".env.template"})

    def __post_init__(self) -> None:
        root = self.project_root.expanduser().resolve()
        object.__setattr__(self, "project_root", root)
        self._validate_project_root(root)

    def resolve_path(self, path: str | Path = ".") -> Path:
        """Resolve a user path and ensure it remains inside the project root."""
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = self.project_root / candidate

        resolved = candidate.resolve()
        try:
            resolved.relative_to(self.project_root)
        except ValueError as exc:
            raise UnsafePathError(f"Path is outside the project root: {path}") from exc
        return resolved

    def relative_path(self, path: Path) -> str:
        """Return a POSIX project-relative path for a resolved path."""
        return path.relative_to(self.project_root).as_posix()

    def is_path_ignored(self, path: Path, *, is_dir: bool | None = None) -> bool:
        """Return whether a resolved path is excluded by built-in policy."""
        if path == self.project_root:
            return False

        relative = path.relative_to(self.project_root)
        parts = relative.parts
        if any(part in self.ignored_dir_names for part in parts[:-1]):
            return True

        name = path.name
        if is_dir is True:
            return name in self.ignored_dir_names

        if self._is_env_file_name(name):
            return True

        if name in self.ignored_file_names:
            return True

        suffixes = [suffix.lower() for suffix in path.suffixes]
        if any(suffix in self.ignored_suffixes for suffix in suffixes):
            return True

        return False

    def ensure_readable_text_file(self, path: Path) -> None:
        """Reject paths that should not be exposed to a model read/search."""
        if path.is_symlink():
            raise RepositoryFileRejected(f"Refusing to inspect symlink: {self.relative_path(path)}")
        if not path.exists() or not path.is_file():
            raise RepositoryFileRejected(f"Path is not a file: {self.relative_path(path)}")
        if self.is_path_ignored(path, is_dir=False):
            raise RepositoryFileRejected(
                f"File is excluded by workspace policy: {self.relative_path(path)}"
            )
        if path.stat().st_size > self.max_file_bytes:
            raise RepositoryFileRejected(
                f"File is larger than {self.max_file_bytes} bytes: {self.relative_path(path)}"
            )
        if _looks_binary(path):
            raise RepositoryFileRejected(f"File appears to be binary: {self.relative_path(path)}")

    def _is_env_file_name(self, name: str) -> bool:
        if name in self.allowed_env_templates:
            return False
        return name == ".env" or name.startswith(".env.")

    @staticmethod
    def _validate_project_root(root: Path) -> None:
        if root == Path(root.anchor):
            raise UnsafeWorkspaceError("Refusing to inspect the filesystem root")
        if root == Path.home().resolve():
            raise UnsafeWorkspaceError("Refusing to inspect the user's home directory")


class RepositoryInspector:
    """Expose bounded, redacted, read-only inspection for one repository."""

    def __init__(self, project_root: str | Path, policy: WorkspacePolicy | None = None) -> None:
        root = Path(project_root)
        self.policy = policy or WorkspacePolicy(root)

    def list_files(self, path: str | Path = ".", limit: int = 200) -> FileListing:
        """Return sorted allowed file paths below a safe repository path."""
        if limit < 1:
            raise RepositoryError("limit must be greater than zero")

        root = self.policy.resolve_path(path)
        allowed_paths: list[str] = []
        if root.is_file():
            if self._can_list_file(root):
                allowed_paths.append(self.policy.relative_path(root))
        elif root.is_dir():
            allowed_paths.extend(self._iter_allowed_files(root))
        else:
            raise RepositoryFileRejected(f"Path does not exist: {path}")

        sorted_paths = sorted(allowed_paths)
        return FileListing(
            paths=sorted_paths[:limit],
            total_count=len(sorted_paths),
            limit=limit,
            truncated=len(sorted_paths) > limit,
        )

    def read_file(self, path: str | Path, offset: int = 0, limit: int = 200) -> FileRead:
        """Read a safe text file by 0-based line offset and line limit."""
        if offset < 0:
            raise RepositoryError("offset must not be negative")
        if limit < 1:
            raise RepositoryError("limit must be greater than zero")

        resolved = self.policy.resolve_path(path)
        self.policy.ensure_readable_text_file(resolved)

        relative_path = self.policy.relative_path(resolved)
        lines = _read_utf8_lines(resolved, relative_path)
        selected = lines[offset : offset + limit]
        redacted_lines = [_redact_secrets(line) for line in selected]
        redacted = any(line.redacted for line in redacted_lines)
        content = "".join(line.text for line in redacted_lines)
        returned_count = len(selected)

        if returned_count:
            start_line = offset + 1
            end_line = offset + returned_count
        else:
            start_line = offset + 1
            end_line = offset

        return FileRead(
            path=relative_path,
            content=content,
            offset=offset,
            limit=limit,
            start_line=start_line,
            end_line=end_line,
            total_lines=len(lines),
            truncated=offset + returned_count < len(lines),
            redacted=redacted,
        )

    def search_text(self, query: str, limit: int = 50) -> TextSearch:
        """Search allowed text files for a query, returning redacted matching lines."""
        if not query:
            raise RepositoryError("query must not be empty")
        if limit < 1:
            raise RepositoryError("limit must be greater than zero")

        query_lower = query.lower()
        matches: list[TextSearchMatch] = []
        redacted_any = False
        truncated = False

        for file_path in self._iter_allowed_files(self.policy.project_root):
            resolved = self.policy.resolve_path(file_path)
            try:
                lines = _read_utf8_lines(resolved, file_path)
            except RepositoryFileRejected:
                continue

            for line_number, line in enumerate(lines, start=1):
                if query_lower not in line.lower():
                    continue

                redacted_line = _redact_secrets(line.rstrip("\n\r"))
                redacted_any = redacted_any or redacted_line.redacted
                if len(matches) >= limit:
                    truncated = True
                    return TextSearch(
                        query=query,
                        matches=matches,
                        limit=limit,
                        truncated=truncated,
                        redacted=redacted_any,
                    )
                matches.append(
                    TextSearchMatch(
                        path=file_path,
                        line_number=line_number,
                        line=redacted_line.text,
                        redacted=redacted_line.redacted,
                    )
                )

        return TextSearch(
            query=query,
            matches=matches,
            limit=limit,
            truncated=truncated,
            redacted=redacted_any,
        )

    def _iter_allowed_files(self, root: Path) -> Iterable[str]:
        if self.policy.is_path_ignored(root, is_dir=root.is_dir()):
            return

        for current_root, dir_names, file_names in os.walk(root):
            current_path = Path(current_root)
            if current_path.is_symlink() or self.policy.is_path_ignored(current_path, is_dir=True):
                dir_names[:] = []
                continue

            dir_names[:] = sorted(
                name
                for name in dir_names
                if not (current_path / name).is_symlink()
                and not self.policy.is_path_ignored(current_path / name, is_dir=True)
            )

            for file_name in sorted(file_names):
                file_path = current_path / file_name
                if self._can_list_file(file_path):
                    yield self.policy.relative_path(file_path)

    def _can_list_file(self, file_path: Path) -> bool:
        try:
            self.policy.ensure_readable_text_file(file_path)
        except RepositoryFileRejected:
            return False
        return True


_SECRET_KEYWORDS = (
    "api[_-]?key",
    "auth",
    "password",
    "passwd",
    "private[_-]?key",
    "secret",
    "token",
    "access[_-]?key",
)
_SECRET_KEY_PATTERN = "|".join(_SECRET_KEYWORDS)
_QUOTED_SECRET_ASSIGNMENT_RE = re.compile(
    rf"(?i)(\b[\w.-]*(?:{_SECRET_KEY_PATTERN})[\w.-]*\s*[:=]\s*)(['\"])([^'\"\n]*)(['\"])",
)
_BARE_SECRET_ASSIGNMENT_RE = re.compile(
    rf"(?i)(\b[\w.-]*(?:{_SECRET_KEY_PATTERN})[\w.-]*\s*[:=]\s*)([^\s#'\"]+)",
)
_BEARER_TOKEN_RE = re.compile(r"(?i)(\bbearer\s+)([A-Za-z0-9._~+/=-]{8,})")


def _redact_secrets(text: str) -> RedactedText:
    redacted = False

    def replace_quoted(match: re.Match[str]) -> str:
        nonlocal redacted
        redacted = True
        return f"{match.group(1)}{match.group(2)}[REDACTED]{match.group(4)}"

    def replace_bare(match: re.Match[str]) -> str:
        nonlocal redacted
        value = match.group(2)
        if value == "[REDACTED]":
            return match.group(0)
        redacted = True
        return f"{match.group(1)}[REDACTED]"

    def replace_bearer(match: re.Match[str]) -> str:
        nonlocal redacted
        redacted = True
        return f"{match.group(1)}[REDACTED]"

    result = _QUOTED_SECRET_ASSIGNMENT_RE.sub(replace_quoted, text)
    result = _BARE_SECRET_ASSIGNMENT_RE.sub(replace_bare, result)
    result = _BEARER_TOKEN_RE.sub(replace_bearer, result)
    return RedactedText(text=result, redacted=redacted)


def _looks_binary(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            chunk = handle.read(4096)
    except OSError as exc:
        raise RepositoryFileRejected(f"Unable to inspect file: {path}") from exc

    return b"\0" in chunk


def _read_utf8_lines(path: Path, relative_path: str) -> list[str]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return handle.readlines()
    except UnicodeDecodeError as exc:
        raise RepositoryFileRejected(f"File is not valid UTF-8 text: {relative_path}") from exc
    except OSError as exc:
        raise RepositoryFileRejected(f"Unable to read file: {relative_path}") from exc
