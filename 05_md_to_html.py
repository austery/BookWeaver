#!/usr/bin/env python3
from __future__ import annotations

import argparse
from html import escape
from pathlib import Path


def parse_alternating_segments(markdown_text: str) -> list[tuple[str, str]]:
    blocks = [block.strip() for block in markdown_text.split("\n---") if block.strip()]
    segments: list[tuple[str, str]] = []

    for block in blocks:
        lines = block.splitlines()
        cleaned = [line for line in lines if not line.strip().startswith("## Segment")]
        text = "\n".join(cleaned).strip()

        marker = "**中文译文**"
        if marker in text:
            source, translated = text.split(marker, 1)
            segments.append((source.strip(), translated.strip()))
        else:
            segments.append((text, ""))
    return segments


def _paragraphs_html(text: str, css_class: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    return "\n".join(f'<p class="{css_class}">{escape(line)}</p>' for line in lines)


def render_alternating_bilingual_html(markdown_text: str) -> str:
    segments = parse_alternating_segments(markdown_text)
    body_parts: list[str] = []
    for source, translated in segments:
        if source:
            body_parts.append(_paragraphs_html(source, "source-text"))
        if translated:
            body_parts.append(_paragraphs_html(translated, "translated-text"))
        body_parts.append('<hr class="segment-separator" />')

    body = "\n".join(part for part in body_parts if part)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>BookWeaver Output</title>
  <style>
    body {{ max-width: 860px; margin: 0 auto; padding: 20px; line-height: 1.7; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }}
    .source-text {{ color: #1f2937; margin: 0.6em 0; }}
    .translated-text {{ color: #0f766e; margin: 0.6em 0 1.1em; font-weight: 500; }}
    .segment-separator {{ border: 0; border-top: 1px solid #e5e7eb; margin: 1.2em 0; }}
  </style>
</head>
<body>
{body}
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Step 5: Convert bilingual markdown to alternating HTML"
    )
    parser.add_argument("--temp-dir", required=True, help="Temp directory path")
    parser.add_argument(
        "--input-md",
        default="output.md",
        help="Input markdown file name inside temp dir (default: output.md)",
    )
    parser.add_argument(
        "--output-html",
        default="book.html",
        help="Output html file name inside temp dir (default: book.html)",
    )
    parser.add_argument(
        "--bilingual-style",
        choices=["alternating"],
        default="alternating",
        help="Bilingual layout style (currently only: alternating)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    temp_dir = Path(args.temp_dir).expanduser().resolve()
    input_path = temp_dir / args.input_md
    output_path = temp_dir / args.output_html

    if not input_path.exists():
        raise SystemExit(f"Input markdown not found: {input_path}")

    markdown_text = input_path.read_text(encoding="utf-8")
    html = render_alternating_bilingual_html(markdown_text)
    output_path.write_text(html, encoding="utf-8")
    print(f"Generated HTML: {output_path}")


if __name__ == "__main__":
    main()
