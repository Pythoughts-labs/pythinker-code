"""Local documentation context for code-reviewr-derived help-docs answers."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from pythinker_review.engine.token_budget import clip_text

_DEFAULT_EXTENSIONS = ("md", "mdx", "rst")
_MAX_DOC_FILES = 500
_MAX_DOC_FILE_CHARS = 8_000


class HelpDocsError(ValueError):
    """Raised when local documentation context cannot be built."""


def load_help_docs_context(
    *,
    repo: Path,
    docs_path: Path,
    include_root_readme: bool,
    extensions: Sequence[str],
    budget_chars: int,
) -> tuple[str, dict[str, str]]:
    """Load a bounded local documentation corpus for help-docs questions."""
    root = repo.resolve()
    docs_root = _resolve_inside_repo(root, docs_path)
    exts = _normalize_extensions(extensions)
    files: list[Path] = []
    if include_root_readme:
        files.extend(_root_readmes(root, exts))
    if docs_root.exists():
        if docs_root.is_file():
            if _matches_extension(docs_root, exts) and _is_safe_file(docs_root, root):
                files.append(docs_root.resolve())
        elif docs_root.is_dir():
            files.extend(_iter_doc_files(docs_root, exts, root))
        else:
            raise HelpDocsError(f"docs path is neither file nor directory: {docs_path}")
    elif not files:
        raise HelpDocsError(f"docs path does not exist: {docs_path}")
    files = _dedupe(files)[:_MAX_DOC_FILES]
    if not files:
        raise HelpDocsError(f"no documentation files found under: {docs_path}")
    parts: list[str] = []
    loaded = 0
    for file in files:
        try:
            content = file.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        if not content:
            continue
        display_path = _display_path(file, root)
        parts.append(
            "\n".join(
                [
                    "==file name==",
                    display_path,
                    "",
                    "==file content==",
                    clip_text(content, _MAX_DOC_FILE_CHARS),
                    "=========",
                ]
            )
        )
        loaded += 1
    if not parts:
        raise HelpDocsError("documentation files were empty or unreadable")
    context = clip_text("\n\n".join(parts), max(500, budget_chars))
    metadata = {
        "source_label": f"local-docs:{_display_path(docs_root, root)}",
        "docs_path": _display_path(docs_root, root),
        "docs_files": str(loaded),
    }
    return context, metadata


def _normalize_extensions(extensions: Sequence[str]) -> tuple[str, ...]:
    normalized = tuple(
        dict.fromkeys(ext.lower().lstrip(".") for ext in (extensions or _DEFAULT_EXTENSIONS) if ext)
    )
    return normalized or _DEFAULT_EXTENSIONS


def _resolve_inside_repo(root: Path, path: Path) -> Path:
    candidate = path if path.is_absolute() else root / path
    if _has_symlink_component(candidate, root):
        raise HelpDocsError(f"docs path contains symlink: {path}")
    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise HelpDocsError(f"docs path escapes repository: {path}") from exc
    return resolved


def _has_symlink_component(path: Path, root: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    if ".." in relative.parts:
        return True
    current = root
    for part in relative.parts:
        current = current / part
        try:
            if current.is_symlink():
                return True
        except OSError:
            return True
    return False


def _is_safe_file(path: Path, root: Path) -> bool:
    try:
        if _has_symlink_component(path, root):
            return False
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError):
        return False
    return resolved.is_file()


def _root_readmes(root: Path, extensions: tuple[str, ...]) -> list[Path]:
    out: list[Path] = []
    for ext in extensions:
        for name in (f"README.{ext}", f"readme.{ext}"):
            candidate = root / name
            if _is_safe_file(candidate, root):
                out.append(candidate.resolve())
    return out


def _iter_doc_files(docs_root: Path, extensions: tuple[str, ...], repo_root: Path) -> list[Path]:
    files: list[Path] = []
    suffixes = {f".{ext}" for ext in extensions}
    for path in sorted(docs_root.rglob("*")):
        if len(files) >= _MAX_DOC_FILES:
            break
        if path.suffix.lower() in suffixes and _is_safe_file(path, repo_root):
            files.append(path.resolve())
    return files


def _matches_extension(path: Path, extensions: tuple[str, ...]) -> bool:
    return path.suffix.lower().lstrip(".") in extensions


def _dedupe(files: Sequence[Path]) -> list[Path]:
    seen: set[Path] = set()
    out: list[Path] = []
    for file in files:
        resolved = file.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        out.append(resolved)
    return out


def _display_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


__all__ = ["HelpDocsError", "load_help_docs_context"]
