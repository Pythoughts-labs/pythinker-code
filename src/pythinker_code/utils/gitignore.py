from __future__ import annotations

from pathlib import Path


def ensure_gitignored(git_root: Path, pattern: str, comment: str = "") -> None:
    """Append *pattern* to <git_root>/.gitignore if not already present.

    Creates .gitignore if the file does not exist. Handles missing trailing
    newline before appending. Prepends a comment line when *comment* is given.
    """
    gi_path = git_root / ".gitignore"

    if gi_path.exists():
        content = gi_path.read_text(encoding="utf-8")
        # Check if pattern is already present as a standalone line
        if any(line.strip() == pattern for line in content.splitlines()):
            return
    else:
        content = ""

    lines_to_append: list[str] = []
    if content and not content.endswith("\n"):
        lines_to_append.append("\n")
    if comment:
        lines_to_append.append(f"# {comment}\n")
    lines_to_append.append(f"{pattern}\n")

    with gi_path.open("a", encoding="utf-8") as f:
        f.write("".join(lines_to_append))
