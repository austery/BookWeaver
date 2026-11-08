"""Check that relative Markdown links in maintained, tracked files resolve.

Rules (``~/Documents/global-skills/agents/DOC-LIFECYCLE.md``, "Link check"):

- every relative link or image resolves to an existing path inside the repository;
- absolute paths, ``~`` paths and ``file:`` links (including ``<file:...>`` autolinks)
  fail: write a machine-specific path in a code span;
- files under ``docs/_archive/`` are byte-preserved history and are skipped, except the
  archive indexes (``docs/_archive/README.md`` and ``docs/_archive/<dir>/README.md``).

Markdown is parsed as CommonMark by ``markdown-it-py``, as the puresubs reference parses it
with mdast, so code blocks, code spans, HTML and escapes are handled by the parser, not by
patterns. Out of scope: heading anchors and external URLs.

Usage: ``uv run python scripts/check_doc_links.py [repository root]``; exits 1 on any
broken link.
"""

from __future__ import annotations

import posixpath
import re
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import unquote

from markdown_it import MarkdownIt
from markdown_it.token import Token

ARCHIVE = "docs/_archive/"
Reason = Literal["missing", "outside-repository", "machine-specific", "unreadable"]

_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*:", re.IGNORECASE)
# A bare filename with an editor line suffix (file.py:12) looks like a URI scheme.
_BARE_FILE_LINE = re.compile(r"^[^:/]+\.[^:/]+:\d+(?:-\d+)?(?:[?#].*)?$")
_LINE_SUFFIX = re.compile(r":\d+(?:-\d+)?$")
_PARSER = MarkdownIt("commonmark")
# markdown-it drops file: and other "unsafe" targets as links; keep every target, so the
# rules below can fail file: links instead of silently ignoring them.
_PARSER.validateLink = lambda url: True  # type: ignore[method-assign]


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


def _attribute(token: Token, name: str) -> str:
    value = token.attrGet(name)
    return value if isinstance(value, str) else ""


def _links(text: str) -> Iterator[tuple[int, str]]:
    """(line number, target) for every link and image, as CommonMark reads them."""
    for block in _PARSER.parse(text):
        if block.type != "inline" or block.map is None or block.children is None:
            continue
        line = block.map[0] + 1
        for token in block.children:
            if token.type in ("softbreak", "hardbreak"):
                line += 1
            elif token.type in ("link_open", "image"):
                target = _attribute(token, "href" if token.type == "link_open" else "src")
                if target:
                    yield line, target


def _link_path(target: str) -> str:
    """The file path part of a target: no fragment, query or editor line suffix."""
    without_fragment = target.split("#", 1)[0].split("?", 1)[0]
    return _LINE_SUFFIX.sub("", without_fragment)


def broken_links_in_text(root: Path, file: str, text: str) -> list[BrokenLink]:
    broken: list[BrokenLink] = []
    for number, encoded in _links(text):
        # The parser percent-encodes targets (spaces, non-ASCII); report them as written.
        target = unquote(encoded)
        if target.lower().startswith("file:") or target.startswith(("/", "~")):
            broken.append(BrokenLink(file, number, target, "machine-specific"))
            continue
        is_uri = _SCHEME.match(target) and not _BARE_FILE_LINE.match(target)
        if is_uri or target.startswith("#"):
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
        try:
            text = (root / name).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            # A tracked file missing from the working tree (a plain mv) or not UTF-8.
            broken.append(BrokenLink(name, 1, type(exc).__name__, "unreadable"))
            continue
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
