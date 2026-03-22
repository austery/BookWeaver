from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ContextParagraph:
    doc_path: str
    text: str
    order: int


@dataclass(frozen=True, slots=True)
class EpubContextArtifacts:
    analysis_path: Path
    prompt_path: Path
    manifest_path: Path
    context_signature: str
    prompt_hash: str
    prompt_text: str


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _group_samples_by_doc(
    *,
    selected_docs: list[str],
    sampled_paragraphs: list[ContextParagraph],
) -> dict[str, list[ContextParagraph]]:
    grouped: dict[str, list[ContextParagraph]] = {doc_path: [] for doc_path in selected_docs}
    for item in sampled_paragraphs:
        bucket = grouped.get(item.doc_path)
        if bucket is not None:
            bucket.append(item)
    return grouped


def _compute_context_signature(
    *,
    selected_docs: list[str],
    sampled_paragraphs: list[ContextParagraph],
    output_lang: str,
    max_paragraphs_per_doc: int,
    max_paragraphs_total: int,
) -> str:
    payload = {
        "selected_docs": selected_docs,
        "sampled_paragraphs": [
            {"doc_path": item.doc_path, "order": item.order, "text": item.text}
            for item in sampled_paragraphs
        ],
        "output_lang": output_lang,
        "max_paragraphs_per_doc": max_paragraphs_per_doc,
        "max_paragraphs_total": max_paragraphs_total,
    }
    serialized = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return _sha256_text(serialized)


def _build_analysis_markdown(
    *,
    selected_docs: list[str],
    sampled_paragraphs: list[ContextParagraph],
    output_lang: str,
) -> str:
    samples_by_doc = _group_samples_by_doc(
        selected_docs=selected_docs,
        sampled_paragraphs=sampled_paragraphs,
    )
    lines: list[str] = [
        "# EPUB Context Analysis",
        "",
        "## Summary",
        f"- Output language: `{output_lang}`",
        f"- Selected context docs: {len(selected_docs)}",
        f"- Sampled paragraphs: {len(sampled_paragraphs)}",
        "",
        "## Selected documents",
    ]

    for doc_path in selected_docs:
        lines.append(f"- `{doc_path}`")

    lines.extend(["", "## Sampled excerpts"])

    for doc_path in selected_docs:
        doc_samples = samples_by_doc[doc_path]
        if not doc_samples:
            continue
        lines.append(f"### `{doc_path}`")
        for item in doc_samples:
            lines.append(f"{item.order + 1}. {item.text}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _build_prompt_text(
    *,
    output_lang: str,
    selected_docs: list[str],
    sampled_paragraphs: list[ContextParagraph],
    context_signature: str,
    custom_prompt: str | None,
) -> str:
    samples_by_doc = _group_samples_by_doc(
        selected_docs=selected_docs,
        sampled_paragraphs=sampled_paragraphs,
    )
    lines: list[str] = [
        f"You are a professional translator for {output_lang}.",
        "",
        "BOOK CONTEXT",
        f"- Context signature: {context_signature}",
        f"- Selected context docs: {len(selected_docs)}",
        "",
        "TRANSLATION REQUIREMENTS",
        "1. Output only translated content.",
        "2. Preserve paragraph count and order exactly.",
        "3. Keep proper nouns, code, and non-translatable terms unchanged when appropriate.",
        "4. If input contains %% separators, preserve them in output.",
        "",
        "CONTEXT EXCERPTS",
    ]

    for doc_path in selected_docs:
        doc_samples = [item.text for item in samples_by_doc[doc_path]]
        if not doc_samples:
            continue
        lines.append(f"- {doc_path}")
        for sample in doc_samples:
            lines.append(f"  - {sample}")

    if custom_prompt:
        lines.extend(["", "ADDITIONAL INSTRUCTIONS", custom_prompt])

    return "\n".join(lines).strip() + "\n"


def run_epub_context_pass(
    *,
    artifacts_dir: Path,
    selected_docs: list[str],
    sampled_paragraphs: list[ContextParagraph],
    output_lang: str,
    max_paragraphs_per_doc: int,
    max_paragraphs_total: int,
    custom_prompt: str | None,
    audience: str | None = None,
    style: str | None = None,
) -> EpubContextArtifacts:
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    analysis_path = artifacts_dir / "01-analysis.md"
    prompt_path = artifacts_dir / "02-prompt.md"
    manifest_path = artifacts_dir / "context_manifest.json"

    context_signature = _compute_context_signature(
        selected_docs=selected_docs,
        sampled_paragraphs=sampled_paragraphs,
        output_lang=output_lang,
        max_paragraphs_per_doc=max_paragraphs_per_doc,
        max_paragraphs_total=max_paragraphs_total,
    )
    analysis_text = _build_analysis_markdown(
        selected_docs=selected_docs,
        sampled_paragraphs=sampled_paragraphs,
        output_lang=output_lang,
    )
    prompt_text = _build_prompt_text(
        output_lang=output_lang,
        selected_docs=selected_docs,
        sampled_paragraphs=sampled_paragraphs,
        context_signature=context_signature,
        custom_prompt=custom_prompt,
    )
    prompt_hash = _sha256_text(prompt_text)

    analysis_path.write_text(analysis_text, encoding="utf-8")
    prompt_path.write_text(prompt_text, encoding="utf-8")

    samples_by_doc = _group_samples_by_doc(
        selected_docs=selected_docs,
        sampled_paragraphs=sampled_paragraphs,
    )
    sampled_counts_by_doc = {doc_path: len(samples_by_doc[doc_path]) for doc_path in selected_docs}

    manifest = {
        "selected_docs": selected_docs,
        "sampled_counts_by_doc": sampled_counts_by_doc,
        "sampled_total": len(sampled_paragraphs),
        "max_paragraphs_per_doc": max_paragraphs_per_doc,
        "max_paragraphs_total": max_paragraphs_total,
        "audience_override": audience,
        "style_override": style,
        "context_signature": context_signature,
        "prompt_hash": prompt_hash,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2), encoding="utf-8")

    return EpubContextArtifacts(
        analysis_path=analysis_path,
        prompt_path=prompt_path,
        manifest_path=manifest_path,
        context_signature=context_signature,
        prompt_hash=prompt_hash,
        prompt_text=prompt_text,
    )
