#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ai.bilingual_merger import BilingualMerger


def _natural_sort_key(path: Path) -> tuple[int, str]:
    stem = path.stem.replace("page", "")
    try:
        return (int(stem), path.name)
    except ValueError:
        return (0, path.name)


def _read_files(paths: list[Path]) -> list[str]:
    """Read markdown files with error handling."""
    contents: list[str] = []
    for path in paths:
        try:
            contents.append(path.read_text(encoding="utf-8").strip())
        except FileNotFoundError:
            raise FileNotFoundError(f"File not found: {path}")
        except IOError as e:
            raise IOError(f"Error reading {path}: {e}")
    return contents


def merge_markdown_files(temp_dir: Path, output_name: str = "output.md") -> Path:
    """Merge source and translation markdown files into bilingual output (Step 4).

    Args:
        temp_dir: Directory containing page*.md and output_page*.md files
        output_name: Name of output file (default: output.md)

    Returns:
        Path to the merged bilingual markdown file

    Raises:
        SystemExit: If files missing or counts don't match
        FileNotFoundError: If source/translation files cannot be read
        IOError: If output file cannot be written
    """
    source_files = sorted(temp_dir.glob("page*.md"), key=_natural_sort_key)
    source_files = [p for p in source_files if not p.name.startswith("output_")]
    translated_files = sorted(temp_dir.glob("output_page*.md"), key=_natural_sort_key)

    if not source_files:
        raise SystemExit(f"No source page*.md files found in {temp_dir}")
    if not translated_files:
        raise SystemExit(f"No translated output_page*.md files found in {temp_dir}")
    if len(source_files) != len(translated_files):
        raise SystemExit(
            f"Translation incomplete: source={len(source_files)}, translated={len(translated_files)}"
        )

    try:
        originals = _read_files(source_files)
        translations = _read_files(translated_files)
    except (FileNotFoundError, IOError) as e:
        print(f"❌ Error reading input files: {e}", file=sys.stderr)
        raise

    merged = BilingualMerger().merge(original_chunks=originals, translated_chunks=translations)

    out_path = temp_dir / output_name
    try:
        out_path.write_text(merged, encoding="utf-8")
    except IOError as e:
        print(f"❌ Error writing output file {out_path}: {e}", file=sys.stderr)
        raise

    return out_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Step 4: merge original+translated markdown into alternating bilingual output"
    )
    parser.add_argument("--temp-dir", required=True, help="Temp directory containing page files")
    parser.add_argument(
        "--output-name",
        default="output.md",
        help="Merged output markdown name (default: output.md)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    temp_dir = Path(args.temp_dir).expanduser().resolve()
    if not temp_dir.exists():
        raise SystemExit(f"Temp directory not found: {temp_dir}")
    out = merge_markdown_files(temp_dir=temp_dir, output_name=args.output_name)
    print(f"Merged bilingual markdown: {out}")


if __name__ == "__main__":
    main()
