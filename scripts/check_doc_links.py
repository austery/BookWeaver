"""Check that relative Markdown links in maintained, tracked files resolve.

Rules (``~/Documents/global-skills/agents/DOC-LIFECYCLE.md``, "Link check"):

- every relative inline link or image resolves to an existing path inside the repository;
- absolute paths and ``file:`` links fail: write a machine-specific path in a code span;
- files under ``docs/_archive/`` are byte-preserved history and are skipped, except the
  archive indexes (``docs/_archive/README.md`` and ``docs/_archive/<dir>/README.md``).

Out of scope: heading anchors, external URLs and reference-style link definitions. Links
inside fenced code blocks and code spans are not links. No third-party dependency.

Usage: ``uv run python scripts/check_doc_links.py [repository root]``; exits 1 on any
broken link.
"""

from __future__ import annotations

import posixpath
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import unquote

ARCHIVE = "docs/_archive/"
Reason = Literal["missing", "outside-repository", "machine-specific"]

_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_CODE_SPAN = re.compile(r"(`+)(.+?)\1", re.DOTALL)
# [text](target) or ![alt](target); text may hold one level of nested brackets.
_INLINE_LINK = re.compile(r"!?\[(?:[^\[\]]|\[[^\[\]]*\])*\]\(\s*(<[^>]*>|[^\s)]+)(?:\s+[^)]*)?\)")
_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*:", re.IGNORECASE)
# A bare filename with an editor line suffix (file.py:12) looks like a URI scheme.
_BARE_FILE_LINE = re.compile(r"^[^:/]+\.[^:/]+:\d+(?:-\d+)?(?:[?#].*)?$")
_LINE_SUFFIX = re.compile(r":\d+(?:-\d+)?$")


@dataclass(frozen=True)
class BrokenLink:
    file: str
    line: int
    target: str
    reason: Reason


def is_maintained(path: str) -> bool:
    if not path.endswith(".md"):
        return False
    if not path.startswith(ARCHIVE):
        return True
    rest = path[len(ARCHIVE) :]
    return rest == "README.md" or re.fullmatch(r"[^/]+/README\.md", rest) is not None


def _prose_lines(text: str) -> list[tuple[int, str]]:
    """Lines outside fenced code blocks, with code spans blanked out."""
    lines: list[tuple[int, str]] = []
    fence: str | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        opening = _FENCE.match(line)
        if fence is not None:
            if opening and opening.group(1)[0] == fence[0] and len(opening.group(1)) >= len(fence):
                fence = None
            continue
        if opening:
            fence = opening.group(1)
            continue
        lines.append((number, _CODE_SPAN.sub(lambda match: " " * len(match.group(0)), line)))
    return lines


def _link_path(target: str) -> str:
    unwrapped = target[1:-1] if target.startswith("<") and target.endswith(">") else target
    without_fragment = unwrapped.split("#", 1)[0].split("?", 1)[0]
    return unquote(_LINE_SUFFIX.sub("", without_fragment))


def broken_links_in_text(root: Path, file: str, text: str) -> list[BrokenLink]:
    broken: list[BrokenLink] = []
    for number, line in _prose_lines(text):
        for match in _INLINE_LINK.finditer(line):
            target = match.group(1)
            bare = target[1:-1] if target.startswith("<") and target.endswith(">") else target
            if bare.lower().startswith("file:") or bare.startswith("/") or bare.startswith("~"):
                broken.append(BrokenLink(file, number, target, "machine-specific"))
                continue
            if (_SCHEME.match(bare) and not _BARE_FILE_LINE.match(bare)) or bare.startswith("#"):
                continue
            path = _link_path(target)
            if not path:
                continue
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(file), path))
            if resolved == ".." or resolved.startswith("../"):
                broken.append(BrokenLink(file, number, target, "outside-repository"))
            elif not (root / resolved).exists():
                broken.append(BrokenLink(file, number, target, "missing"))
    return broken


def find_broken_links(root: Path) -> list[BrokenLink]:
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.md"],
        cwd=root,
        capture_output=True,
        check=True,
    ).stdout.decode("utf-8")
    files = [name for name in listed.split("\0") if name and is_maintained(name)]
    if not files:
        raise SystemExit("No maintained Markdown files found; is this a git checkout?")
    broken: list[BrokenLink] = []
    for name in files:
        text = (root / name).read_text(encoding="utf-8")
        broken.extend(broken_links_in_text(root, name, text))
    return broken


def main(argv: list[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parent.parent
    broken = find_broken_links(root)
    for link in broken:
        print(f"{link.file}:{link.line}: {link.reason} link target {link.target}", file=sys.stderr)
    if broken:
        print(f"{len(broken)} broken Markdown link(s).", file=sys.stderr)
        return 1
    print("All relative Markdown links in maintained files resolve.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
