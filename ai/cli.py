"""Command-line parsing and application dispatch."""

from __future__ import annotations

import argparse
import sys
import json
from dataclasses import asdict
from pathlib import Path

from ai import orchestration


def build_parser() -> argparse.ArgumentParser:
    """Build the supported application CLI and explicit migration errors."""
    p = argparse.ArgumentParser(
        prog="bookweaver",
        description="Translate EPUB books through Antigravity or a metered model API.",
        epilog="List the named rows for --row with: bookweaver rows",
    )
    p.add_argument(
        "input_path",
        help="Source EPUB file",
    )
    p.add_argument("--output", required=True, help="Output path")
    p.add_argument("--output-lang", default="zh", help="Target language code (default: zh)")
    p.add_argument(
        "--model",
        choices=["flash", "pro"],
        default="flash",
        help="Logical model profile (default: flash)",
    )
    p.add_argument("--effort", choices=["low", "medium", "high"], default=None)
    p.add_argument(
        "--row",
        choices=[row.name for row in orchestration.enabled_rows()],
        metavar="NAME",
        default=None,
        help="Named row in place of --model, --effort and --provider; list with `bookweaver rows`",
    )
    p.add_argument("--allow-paid-api", action="store_true")
    p.add_argument(
        "--allow-isolated-format",
        action="store_true",
        help="Opt in to isolated Markdown/PDF translation",
    )
    p.add_argument(
        "--provider",
        choices=["cli", "gemini", "openai", "anthropic", "api"],
        metavar="{cli,gemini,openai,anthropic}",
        default="cli",
        help="Translation backend: cli is Antigravity; gemini/openai/anthropic are metered APIs (default: cli)",
    )
    p.add_argument("-p", "--prompt", default=None, help="Additional translation instructions")
    p.add_argument(
        "--extract-glossary",
        action="store_true",
        help="Auto-extract glossary before translation (EPUB input only)",
    )
    p.add_argument("--glossary", default=None, help="Path to extracted glossary JSON")
    p.add_argument(
        "--glossary-mode",
        choices=["auto", "deep-scan"],
        default=None,
        help="Glossary request mode: auto (quick extraction) or deep-scan (comprehensive extraction)",
    )
    p.add_argument(
        "--glossary-min-priority",
        default=None,
        choices=["critical", "high", "medium"],
        help="Minimum glossary term priority",
    )
    p.add_argument(
        "--glossary-max-terms",
        type=int,
        default=None,
        help="Max terms when auto-extracting glossary (EPUB input only)",
    )
    p.add_argument(
        "--cli-api-fallback",
        action="store_true",
        help=(
            "Removed: choose a metered --provider (gemini, openai, or anthropic) "
            "with explicit authorization instead."
        ),
    )
    p.add_argument(
        "--max-batch-chars",
        type=int,
        default=None,
        help="Max chars per batch (EPUB default: 60000)",
    )
    p.add_argument(
        "--max-batch-segments",
        type=int,
        default=None,
        help="Maximum segments per batch (EPUB default: 200)",
    )
    p.add_argument(
        "--input-format",
        choices=["auto", "epub"],
        default="auto",
        help="Input format (default: auto-detect from path)",
    )
    p.add_argument(
        "--resume",
        action="store_true",
        default=True,
        help="Resume from checkpoint artifacts when available (EPUB workflow, default: enabled)",
    )
    p.add_argument(
        "--no-resume",
        action="store_false",
        dest="resume",
        help="Disable checkpoint resume for this run",
    )
    p.add_argument(
        "--force-resume",
        action="store_true",
        help="Resume despite model/config mismatches; input/signature mismatches still fail (EPUB workflow)",
    )
    p.add_argument(
        "--checkpoint-dir",
        default=None,
        help="Checkpoint directory path (default: <output-dir>/.bookweaver_checkpoints/<format>/<input-stem>)",
    )
    p.add_argument(
        "--no-sanity-probe",
        action="store_true",
        default=False,
        help="Disable per-batch sanity warnings (observational; never halts) and heartbeat sample output.",
    )
    return p


def _is_model_flag_explicit(argv: list[str] | None) -> bool:
    import sys

    args = argv if argv is not None else sys.argv[1:]
    return any(token == "--model" or token.startswith("--model=") for token in args)


def _format_rows(rows: tuple[orchestration.Row, ...]) -> str:
    """Plain table: one row per line, evidence last because it is free text."""
    header = ("ROW", "PROVIDER", "MODEL", "STATUS", "LAYER", "EVIDENCE")
    lines = [
        (
            row.name,
            row.provider,
            row.model_id,
            row.status,
            "-" if row.layer is None else str(row.layer),
            row.evidence or ("paid; needs --allow-paid-api" if row.provider != "cli" else ""),
        )
        for row in rows
    ]
    widths = [max(len(line[i]) for line in (header, *lines)) for i in range(len(header) - 1)]
    return "\n".join(
        "  ".join(cell.ljust(width) for cell, width in zip(line, widths, strict=False))
        + "  "
        + line[-1]
        for line in (header, *lines)
    )


def rows_main(tokens: list[str]) -> None:
    """`bookweaver rows`: list the enabled named rows."""
    parser = argparse.ArgumentParser(
        prog="bookweaver rows", description="List the enabled named rows for --row."
    )
    parser.add_argument("--json", action="store_true", help="Print rows as JSON")
    args = parser.parse_args(tokens)
    rows = orchestration.enabled_rows()
    if args.json:
        print(json.dumps([asdict(row) for row in rows], indent=2))
    else:
        print(_format_rows(rows))


def _apply_row(
    parser: argparse.ArgumentParser, args: argparse.Namespace, tokens: list[str]
) -> None:
    """Replace --model/--effort/--provider with the named row; reject mixing them."""
    # Reparse with empty defaults so explicit flags are detected even when abbreviated.
    probe = build_parser()
    probe.set_defaults(model=None, provider=None)
    explicit = probe.parse_args(tokens)
    mixed = [
        flag
        for flag, value in (
            ("--model", explicit.model),
            ("--effort", explicit.effort),
            ("--provider", explicit.provider),
        )
        if value is not None
    ]
    if mixed:
        parser.error(f"--row replaces {', '.join(mixed)}; pass only --row")
    row = orchestration.find_row(args.row)
    args.model, args.effort, args.provider = row.profile, row.effort, row.provider


def main(argv: list[str] | None = None) -> None:
    """Parse intent and dispatch to a format-specific application boundary."""
    tokens = argv if argv is not None else sys.argv[1:]
    if tokens[:1] == ["rows"]:
        rows_main(tokens[1:])
        return
    parser = build_parser()
    args = parser.parse_args(tokens)
    if args.row is not None:
        _apply_row(parser, args, tokens)
    if args.provider == "api":
        parser.error("--provider api was renamed; use --provider gemini")
    if args.cli_api_fallback:
        parser.error(
            "Automatic paid API fallback was removed; choose a metered --provider "
            "(gemini, openai, or anthropic) with explicit authorization"
        )
    path = Path(args.input_path)
    fmt = (
        "markdown"
        if path.is_dir()
        else {".epub": "epub", ".md": "markdown", ".pdf": "pdf"}.get(path.suffix.lower())
    )
    if fmt is None:
        parser.error("Unsupported format; EPUB is supported, DOCX is retired")
    if args.input_format == "epub" and fmt != "epub":
        parser.error("--input-format epub requires an EPUB input")
    if fmt != "epub":
        if not args.allow_isolated_format:
            parser.error("Markdown/PDF require --allow-isolated-format")
        if "--resume" in tokens or args.force_resume or args.checkpoint_dir:
            parser.error("Explicit resume is EPUB-only")
        if args.extract_glossary or args.glossary_mode or args.glossary:
            parser.error("Glossary options are EPUB-only")
    spec = orchestration.TranslationSpec(args.output_lang, args.prompt)
    model = orchestration.ModelSpec(
        args.model, args.effort, args.row is not None or _is_model_flag_explicit(tokens)
    )
    provider = orchestration.ProviderSpec(args.provider, args.allow_paid_api)
    quality = orchestration.QualityPolicy(
        not args.no_sanity_probe, args.max_batch_chars, args.max_batch_segments
    )
    if fmt == "epub":
        options = orchestration.EpubTranslationOptions(
            spec=spec,
            model=model,
            provider=provider,
            quality=quality,
            glossary=orchestration.GlossarySpec(
                Path(args.glossary) if args.glossary else None,
                args.glossary_mode,
                args.extract_glossary,
                args.glossary_min_priority,
                args.glossary_max_terms,
            ),
            resume=orchestration.ResumePolicy(
                args.resume,
                args.force_resume,
                Path(args.checkpoint_dir) if args.checkpoint_dir else None,
            ),
        )
        orchestration.translate_epub(path, Path(args.output), options)
    elif fmt == "markdown":
        orchestration.translate_markdown(
            path,
            Path(args.output),
            orchestration.MarkdownTranslationOptions(
                spec=spec,
                model=model,
                provider=provider,
                quality=quality,
            ),
        )
    else:
        orchestration.translate_pdf(
            path,
            Path(args.output),
            orchestration.PdfTranslationOptions(
                spec=spec,
                model=model,
                provider=provider,
                quality=quality,
            ),
        )


if __name__ == "__main__":
    main()
