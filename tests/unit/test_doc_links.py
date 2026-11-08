"""The documentation link check, run as the command the verification steps use."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_doc_links.py"


def make_repo(tmp_path: Path, files: dict[str, str]) -> Path:
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    return tmp_path


def check(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(root)], capture_output=True, text=True, check=False
    )


def test_resolving_links_pass(tmp_path: Path) -> None:
    root = make_repo(
        tmp_path,
        {
            "README.md": "[spec](docs/spec.md) ![logo](<docs/my logo.png>) [web](https://x.y)\n"
            "[anchor](#top) [line](docs/spec.md:12) [frag](docs/spec.md#part)\n",
            "docs/spec.md": '[back](../README.md "title")\n',
            "docs/my logo.png": "",
        },
    )
    result = check(root)
    assert result.returncode == 0, result.stderr


def test_broken_links_fail_with_their_reason(tmp_path: Path) -> None:
    root = make_repo(
        tmp_path,
        {
            "README.md": "[gone](docs/missing.md)\n"
            "[abs](/Users/someone/notes.md)\n"
            "[uri](file:///tmp/x.md)\n"
            "[home](~/notes.md)\n"
            "[up](../outside.md)\n",
        },
    )
    result = check(root)
    assert result.returncode == 1
    assert "README.md:1: missing" in result.stderr
    assert "README.md:2: machine-specific" in result.stderr
    assert "README.md:3: machine-specific" in result.stderr
    assert "README.md:4: machine-specific" in result.stderr
    assert "README.md:5: outside-repository" in result.stderr
    assert "5 broken Markdown link(s)." in result.stderr


def test_code_is_not_checked(tmp_path: Path) -> None:
    root = make_repo(
        tmp_path,
        {
            "README.md": "Use `[x](/abs/path.md)` inline.\n\n"
            "```markdown\n[y](missing.md)\n```\n\n"
            "~~~\n[z](/abs.md)\n~~~\n",
        },
    )
    assert check(root).returncode == 0


def test_archive_payload_is_skipped_but_its_index_is_checked(tmp_path: Path) -> None:
    root = make_repo(
        tmp_path,
        {
            "README.md": "ok\n",
            "docs/_archive/2026/old-plan.md": "[gone](nowhere.md)\n",
            "docs/_archive/README.md": "[plan](2026/old-plan.md) [lost](2026/lost.md)\n",
        },
    )
    result = check(root)
    assert result.returncode == 1
    assert "docs/_archive/README.md:1: missing link target 2026/lost.md" in result.stderr
    assert "docs/_archive/2026/old-plan.md:" not in result.stderr


def test_parentheses_in_a_target_are_part_of_it(tmp_path: Path) -> None:
    root = make_repo(
        tmp_path,
        {"README.md": "[x](docs/a(b).md) [y](docs/c(d).md)\n", "docs/a(b).md": "a\n"},
    )
    result = check(root)
    assert result.returncode == 1
    assert "missing link target docs/c(d).md" in result.stderr
    assert "docs/a(b" not in result.stderr


def test_a_link_split_across_lines_is_checked(tmp_path: Path) -> None:
    root = make_repo(
        tmp_path,
        {"README.md": "intro\n[gone](\nmissing.md) and [abs\ntext](/Users/someone/n.md)\n"},
    )
    result = check(root)
    assert result.returncode == 1
    assert "README.md:2: missing link target missing.md" in result.stderr
    assert "README.md:2: machine-specific link target /Users/someone/n.md" in result.stderr


def test_file_autolinks_fail(tmp_path: Path) -> None:
    root = make_repo(tmp_path, {"README.md": "See <file:///Users/x/notes.md> and <https://x.y>.\n"})
    result = check(root)
    assert result.returncode == 1
    assert "README.md:1: machine-specific link target file:///Users/x/notes.md" in result.stderr
    assert "1 broken Markdown link(s)." in result.stderr


def test_indented_code_is_not_checked_but_list_content_is(tmp_path: Path) -> None:
    root = make_repo(
        tmp_path,
        {
            "README.md": "Intro.\n\n    [code](missing-indented.md)\n\n"
            "- item\n\n    ```\n    [fenced](missing-in-fence.md)\n    ```\n\n"
            "    [continued](missing-in-list.md)\n",
        },
    )
    result = check(root)
    assert result.returncode == 1
    assert "missing-in-list.md" in result.stderr
    assert "missing-indented.md" not in result.stderr
    assert "missing-in-fence.md" not in result.stderr


def test_escapes_and_angle_brackets_are_removed_from_targets(tmp_path: Path) -> None:
    root = make_repo(
        tmp_path,
        {"README.md": "[e](\\_notes.md) [a](<docs/x y.md>)\n", "_notes.md": "n\n"},
    )
    result = check(root)
    assert result.returncode == 1
    assert "missing link target docs/x y.md" in result.stderr
    assert "_notes.md" not in result.stderr


def test_markdown_that_is_not_a_link_is_not_checked(tmp_path: Path) -> None:
    root = make_repo(
        tmp_path,
        {
            "README.md": "```\ncode\n```bash\n[a](missing-a.md)\n```\n\n"
            "`span\n[b](missing-b.md)` <!-- [c](missing-c.md) --> \\[d\\](missing-d.md)\n",
        },
    )
    result = check(root)
    assert result.returncode == 0, result.stderr


def test_an_image_inside_a_link_is_checked(tmp_path: Path) -> None:
    root = make_repo(tmp_path, {"README.md": "[![badge](missing.png)](README.md)\n"})
    result = check(root)
    assert result.returncode == 1
    assert "missing link target missing.png" in result.stderr


def test_unreadable_tracked_file_is_reported(tmp_path: Path) -> None:
    root = make_repo(tmp_path, {"README.md": "ok\n", "docs/gone.md": "x\n"})
    (root / "docs" / "gone.md").unlink()
    result = check(root)
    assert result.returncode == 1
    assert "docs/gone.md:1: unreadable" in result.stderr


def test_archive_subdirectory_index_is_checked(tmp_path: Path) -> None:
    root = make_repo(
        tmp_path,
        {"README.md": "ok\n", "docs/_archive/2026/README.md": "[lost](lost.md)\n"},
    )
    result = check(root)
    assert result.returncode == 1
    assert "docs/_archive/2026/README.md:1: missing" in result.stderr
