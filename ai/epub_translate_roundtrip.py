from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import hashlib
import re
import subprocess
import zipfile
from typing import Callable

from ai.epub_package import (
    EpubPackageModel,
    _read_zip_text,
    extract_translatable_segments,
    load_epub_package,
    patch_xhtml_alternating,
    repack_epub_with_overrides,
    resolve_opf_href,
    validate_fragment_links,
    validate_manifest_assets,
    validate_package_structure,
)
from ai.gemini_provider import GeminiProvider
from pipeline_utils import get_language_name as _get_language_name

TranslateFn = Callable[[str], str]
# _MODEL_ALIASES is independent from the config.json alias table loaded by
# load_runtime_config(). This local table maps short CLI names to full EPUB
# workflow model identifiers and is not affected by user config overrides.
_MODEL_ALIASES = {
    "pro": "gemini-3-pro-preview",
    "flash": "gemini-2.5-flash",
    "lite": "gemini-2.5-flash-lite",
}
_PRO_PREBATCH_MAX_CHARS: int = 60_000  # TODO(SPEC-007): move to config.json
_SEGMENT_DELIMITER = "%%"
_BATCH_SEPARATOR = f"\n\n{_SEGMENT_DELIMITER}\n\n"
_BATCH_SPLIT_PATTERN = re.compile(rf"\n\s*{re.escape(_SEGMENT_DELIMITER)}\s*\n")
_IMMERSIVE_SYSTEM_PROMPT_TEMPLATE = """You are a professional {target_language} native translator who needs to fluently translate text into {target_language}.

## Translation Rules
1. Output only the translated content, without explanations or additional content (such as "Here's the translation:" or "Translation as follows:")
2. The returned translation must maintain exactly the same number of paragraphs and format as the original text
3. If the text contains HTML tags, consider where the tags should be placed in the translation while maintaining fluency
4. For content that should not be translated (such as proper nouns, code, etc.), keep the original text.
5. If input contains %%, use %% in your output, if input has no %%, don't use %% in your output

## OUTPUT FORMAT:
- Single paragraph input -> Output translation directly (no separators, no extra text)
- Multi-paragraph input -> Use %% as paragraph separator between translations
"""
_IMMERSIVE_SINGLE_PROMPT_TEMPLATE = "Translate to {target_language} (output translation only):"
_IMMERSIVE_MULTI_PROMPT_TEMPLATE = "Translate to {target_language}:"


@dataclass(frozen=True, slots=True)
class TranslateRoundtripResult:
    output_epub: Path
    translated_segments: int
    translated_docs: int


@dataclass(frozen=True, slots=True)
class CheckpointEntry:
    doc_path: str
    checkpoint_file: str
    segments: int


@dataclass(frozen=True, slots=True)
class CheckpointSnapshot:
    overrides: dict[str, bytes]
    entries: dict[str, CheckpointEntry]
    translated_segments: int
    translated_docs: int


def _create_translation_prompt(
    output_lang: str,
    custom_prompt: str | None,
    *,
    segment_count: int,
) -> str:
    language_name = _get_language_name(output_lang)
    base_prompt = _IMMERSIVE_SYSTEM_PROMPT_TEMPLATE.format(target_language=language_name)

    user_prompt = _IMMERSIVE_SINGLE_PROMPT_TEMPLATE
    if segment_count > 1:
        user_prompt = _IMMERSIVE_MULTI_PROMPT_TEMPLATE
    base_prompt = f"{base_prompt}\n{user_prompt.format(target_language=language_name)}"

    if custom_prompt:
        return f"{base_prompt}\n\nADDITIONAL INSTRUCTIONS:\n{custom_prompt}"
    return base_prompt


def _resolve_model_name(model: str) -> str:
    resolved = _MODEL_ALIASES.get(model.strip(), model.strip())
    if not resolved:
        raise ValueError("model must be a non-empty string")
    return resolved


def _compute_source_signature(source_epub: Path) -> str:
    stat = source_epub.stat()
    signature_payload = (f"{source_epub.resolve()}|{stat.st_size}|{stat.st_mtime_ns}").encode(
        "utf-8"
    )
    return hashlib.sha256(signature_payload).hexdigest()


def _checkpoint_state_file(checkpoint_dir: Path) -> Path:
    return checkpoint_dir / "state.json"


def _checkpoint_docs_dir(checkpoint_dir: Path) -> Path:
    return checkpoint_dir / "docs"


def _checkpoint_doc_filename(doc_path: str) -> str:
    digest = hashlib.sha256(doc_path.encode("utf-8")).hexdigest()
    return f"{digest}.xhtml"


def _write_checkpoint_state(
    *,
    checkpoint_dir: Path,
    source_signature: str,
    output_lang: str,
    bilingual_style: str,
    model: str,
    custom_prompt: str | None,
    entries: dict[str, CheckpointEntry],
) -> None:
    state = {
        "version": 1,
        "source_signature": source_signature,
        "output_lang": output_lang,
        "bilingual_style": bilingual_style,
        "model": model,
        "custom_prompt": custom_prompt,
        "completed_docs": [
            {
                "doc_path": entry.doc_path,
                "checkpoint_file": entry.checkpoint_file,
                "segments": entry.segments,
            }
            for entry in sorted(entries.values(), key=lambda item: item.doc_path)
        ],
    }
    _checkpoint_state_file(checkpoint_dir).write_text(
        json.dumps(state, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )


def _load_checkpoint_snapshot(
    *,
    checkpoint_dir: Path | None,
    source_signature: str,
    output_lang: str,
    bilingual_style: str,
    model: str,
    custom_prompt: str | None,
) -> CheckpointSnapshot:
    if checkpoint_dir is None:
        return CheckpointSnapshot(
            overrides={},
            entries={},
            translated_segments=0,
            translated_docs=0,
        )

    state_file = _checkpoint_state_file(checkpoint_dir)
    if not state_file.exists():
        return CheckpointSnapshot(
            overrides={},
            entries={},
            translated_segments=0,
            translated_docs=0,
        )

    raw_state = json.loads(state_file.read_text(encoding="utf-8"))
    if not isinstance(raw_state, dict):
        raise RuntimeError(f"Invalid checkpoint state format: {state_file}")

    if raw_state.get("source_signature") != source_signature:
        print("[WARN] Checkpoint invalidated: source file changed. Starting fresh.", flush=True)
        return CheckpointSnapshot(
            overrides={},
            entries={},
            translated_segments=0,
            translated_docs=0,
        )
    if raw_state.get("output_lang") != output_lang:
        print(
            f"[WARN] Checkpoint invalidated: output_lang changed ({raw_state.get('output_lang')} -> {output_lang}). Starting fresh.",
            flush=True,
        )
        return CheckpointSnapshot(
            overrides={},
            entries={},
            translated_segments=0,
            translated_docs=0,
        )
    if raw_state.get("bilingual_style") != bilingual_style:
        print(
            f"[WARN] Checkpoint invalidated: bilingual_style changed ({raw_state.get('bilingual_style')} -> {bilingual_style}). Starting fresh.",
            flush=True,
        )
        return CheckpointSnapshot(
            overrides={},
            entries={},
            translated_segments=0,
            translated_docs=0,
        )
    if raw_state.get("model") != model:
        print(
            f"[WARN] Checkpoint invalidated: model changed ({raw_state.get('model')} -> {model}). Starting fresh.",
            flush=True,
        )
        return CheckpointSnapshot(
            overrides={},
            entries={},
            translated_segments=0,
            translated_docs=0,
        )
    if raw_state.get("custom_prompt") != custom_prompt:
        print("[WARN] Checkpoint invalidated: custom_prompt changed. Starting fresh.", flush=True)
        return CheckpointSnapshot(
            overrides={},
            entries={},
            translated_segments=0,
            translated_docs=0,
        )

    completed_docs = raw_state.get("completed_docs")
    if not isinstance(completed_docs, list):
        raise RuntimeError(f"Invalid checkpoint completed_docs format: {state_file}")

    docs_dir = _checkpoint_docs_dir(checkpoint_dir)
    overrides: dict[str, bytes] = {}
    entries: dict[str, CheckpointEntry] = {}
    translated_segments = 0
    for item in completed_docs:
        if not isinstance(item, dict):
            raise RuntimeError(f"Invalid checkpoint entry format in {state_file}")
        doc_path = item.get("doc_path")
        checkpoint_file = item.get("checkpoint_file")
        segments = item.get("segments")
        if not isinstance(doc_path, str) or not isinstance(checkpoint_file, str):
            raise RuntimeError(f"Invalid checkpoint entry fields in {state_file}")
        if not isinstance(segments, int):
            raise RuntimeError(f"Invalid checkpoint segment count in {state_file}")
        checkpoint_path = docs_dir / checkpoint_file
        if not checkpoint_path.exists():
            raise RuntimeError(f"Checkpoint file missing: {checkpoint_path}")
        overrides[doc_path] = checkpoint_path.read_bytes()
        entries[doc_path] = CheckpointEntry(
            doc_path=doc_path,
            checkpoint_file=checkpoint_file,
            segments=segments,
        )
        translated_segments += segments

    return CheckpointSnapshot(
        overrides=overrides,
        entries=entries,
        translated_segments=translated_segments,
        translated_docs=len(entries),
    )


def _persist_checkpoint_doc(
    *,
    checkpoint_dir: Path | None,
    source_signature: str,
    output_lang: str,
    bilingual_style: str,
    model: str,
    custom_prompt: str | None,
    doc_path: str,
    patched_xhtml_bytes: bytes,
    segment_count: int,
    entries: dict[str, CheckpointEntry],
) -> dict[str, CheckpointEntry]:
    if checkpoint_dir is None:
        return entries

    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    docs_dir = _checkpoint_docs_dir(checkpoint_dir)
    docs_dir.mkdir(parents=True, exist_ok=True)

    filename = _checkpoint_doc_filename(doc_path)
    checkpoint_path = docs_dir / filename
    checkpoint_path.write_bytes(patched_xhtml_bytes)

    updated_entries = dict(entries)
    updated_entries[doc_path] = CheckpointEntry(
        doc_path=doc_path,
        checkpoint_file=filename,
        segments=segment_count,
    )
    _write_checkpoint_state(
        checkpoint_dir=checkpoint_dir,
        source_signature=source_signature,
        output_lang=output_lang,
        bilingual_style=bilingual_style,
        model=model,
        custom_prompt=custom_prompt,
        entries=updated_entries,
    )
    return updated_entries


def join_segments_for_batch(segments: list[str]) -> str:
    if not segments:
        return ""
    if len(segments) == 1:
        return segments[0]
    return _BATCH_SEPARATOR.join(segments)


def plan_segment_batches(
    segments: list[str],
    *,
    max_batch_chars: int,
) -> list[list[str]]:
    """Group segments into batches limited by total character count.

    A single segment that exceeds ``max_batch_chars`` is placed alone in its
    own batch (never split). Segment order is preserved across all batches.

    Args:
        segments: Flat list of segment strings to batch.
        max_batch_chars: Maximum total character count per batch (joining
            separators included).

    Returns:
        List of batches, each batch being a non-empty list of segments.
    """
    if max_batch_chars <= 0:
        raise ValueError("max_batch_chars must be > 0")
    if not segments:
        return []

    planned_batches: list[list[str]] = []
    current_batch: list[str] = []
    current_chars = 0

    for segment in segments:
        segment_len = len(segment)
        separator_len = len(_BATCH_SEPARATOR) if current_batch else 0
        next_chars = current_chars + separator_len + segment_len

        if current_batch and next_chars > max_batch_chars:
            planned_batches.append(current_batch)
            current_batch = [segment]
            current_chars = segment_len
            continue

        current_batch.append(segment)
        current_chars = next_chars

    if current_batch:
        planned_batches.append(current_batch)

    return planned_batches


def split_batch_translation(output_text: str, expected_count: int) -> list[str]:
    if expected_count < 0:
        raise ValueError("expected_count must be >= 0")
    if expected_count == 0:
        return []

    normalized = output_text.strip()
    if expected_count == 1:
        if _BATCH_SEPARATOR in normalized or _BATCH_SPLIT_PATTERN.search(normalized):
            raise ValueError("batch translation count mismatch: expected 1, got multiple")
        return [normalized]

    segments = [part.strip() for part in normalized.split(_BATCH_SEPARATOR)]
    if len(segments) != expected_count:
        segments = [part.strip() for part in _BATCH_SPLIT_PATTERN.split(normalized)]

    if len(segments) != expected_count:
        raise ValueError(
            f"batch translation count mismatch: expected {expected_count}, got {len(segments)}"
        )
    return segments


def translate_segments_with_batch_retry(
    segments: list[str],
    *,
    translate_batch: TranslateFn,
    context_label: str,
    retry_depth: int = 0,
) -> list[str]:
    expected_count = len(segments)
    if expected_count == 0:
        return []

    batch_text = join_segments_for_batch(segments)

    def split_and_retry(reason: str, exc: Exception) -> list[str]:
        if expected_count == 1:
            raise RuntimeError(
                f"Batch translation failed at minimal granularity for {context_label}: {reason}"
            ) from exc

        split_index = expected_count // 2
        print(
            f"[WARN] [{context_label}] {reason} at depth={retry_depth}, "
            f"splitting {expected_count} -> {split_index}+{expected_count - split_index}",
            flush=True,
        )

        left = translate_segments_with_batch_retry(
            segments[:split_index],
            translate_batch=translate_batch,
            context_label=context_label,
            retry_depth=retry_depth + 1,
        )
        right = translate_segments_with_batch_retry(
            segments[split_index:],
            translate_batch=translate_batch,
            context_label=context_label,
            retry_depth=retry_depth + 1,
        )
        return left + right

    try:
        translated_batch = str(translate_batch(batch_text))
    except subprocess.TimeoutExpired as exc:
        timeout_value = exc.timeout if isinstance(exc.timeout, (int, float)) else "unknown"
        return split_and_retry(f"Batch request timed out after {timeout_value}s", exc)

    try:
        return split_batch_translation(translated_batch, expected_count=expected_count)
    except ValueError as exc:
        return split_and_retry("Batch output mismatch", exc)


def _resolve_spine_xhtml_paths(model: EpubPackageModel) -> list[str]:
    spine_paths: list[str] = []
    for itemref in model.spine_itemrefs:
        manifest_item = model.manifest_items.get(itemref)
        if manifest_item is None:
            continue
        if manifest_item.media_type != "application/xhtml+xml":
            continue
        spine_paths.append(resolve_opf_href(model.opf_path, manifest_item.href))
    return spine_paths


def _resolve_manifest_xhtml_paths(model: EpubPackageModel) -> list[str]:
    return [
        resolve_opf_href(model.opf_path, item.href)
        for item in model.manifest_items.values()
        if item.media_type == "application/xhtml+xml"
    ]


def _resolve_manifest_paths(model: EpubPackageModel) -> list[str]:
    return [resolve_opf_href(model.opf_path, item.href) for item in model.manifest_items.values()]


def _validate_integrity(
    *,
    model: EpubPackageModel,
    existing_paths: set[str],
    docs: dict[str, str],
    allowed_broken_links: set[str] | None = None,
) -> None:
    errors: list[str] = []
    errors.extend(validate_package_structure(model).errors)

    manifest_paths = _resolve_manifest_paths(model)
    missing_assets = validate_manifest_assets(manifest_paths, existing_paths).missing_paths
    for path in missing_assets:
        errors.append(f"missing manifest asset: {path}")

    allowed = allowed_broken_links or set()
    broken_links = validate_fragment_links(docs).broken_links
    unexpected_broken_links = sorted(link for link in broken_links if link not in allowed)
    for link in unexpected_broken_links:
        errors.append(f"broken fragment link: {link}")

    if errors:
        raise RuntimeError("; ".join(errors))


def run_translate_roundtrip(
    *,
    source_epub: Path,
    output_epub: Path,
    output_lang: str,
    bilingual_style: str,
    model: str,
    custom_prompt: str | None = None,
    translate_fn: TranslateFn | None = None,
    checkpoint_dir: Path | None = None,
) -> TranslateRoundtripResult:
    if bilingual_style != "alternating":
        raise ValueError("Only 'alternating' bilingual style is supported")

    resolved_model = _resolve_model_name(model)
    package_model = load_epub_package(source_epub)
    provider = GeminiProvider(model=resolved_model)
    source_signature = _compute_source_signature(source_epub)
    checkpoint = _load_checkpoint_snapshot(
        checkpoint_dir=checkpoint_dir,
        source_signature=source_signature,
        output_lang=output_lang,
        bilingual_style=bilingual_style,
        model=resolved_model,
        custom_prompt=custom_prompt,
    )
    overrides: dict[str, bytes] = dict(checkpoint.overrides)
    checkpoint_entries: dict[str, CheckpointEntry] = dict(checkpoint.entries)
    translated_segments = checkpoint.translated_segments
    translated_docs = checkpoint.translated_docs
    spine_docs = _resolve_spine_xhtml_paths(package_model)
    manifest_xhtml_paths = _resolve_manifest_xhtml_paths(package_model)
    print(
        f"[INFO] Loaded package: {source_epub.name}, "
        f"spine docs={len(spine_docs)}, model={resolved_model}",
        flush=True,
    )

    with zipfile.ZipFile(source_epub, "r") as source_zip:
        source_docs: dict[str, str] = {
            xhtml_path: _read_zip_text(source_zip, xhtml_path)
            for xhtml_path in manifest_xhtml_paths
        }
        source_broken_links = set(validate_fragment_links(source_docs).broken_links)

        for doc_index, doc_path in enumerate(spine_docs, start=1):
            if doc_path in checkpoint_entries:
                print(
                    f"[INFO] [{doc_index}/{len(spine_docs)}] "
                    f"Resume skip {doc_path} (checkpoint hit)",
                    flush=True,
                )
                continue
            source_xhtml = _read_zip_text(source_zip, doc_path)
            segments = extract_translatable_segments(source_xhtml)
            if not segments:
                print(
                    f"[INFO] [{doc_index}/{len(spine_docs)}] Skip {doc_path} (no translatable segments)",
                    flush=True,
                )
                continue
            print(
                f"[INFO] [{doc_index}/{len(spine_docs)}] Translating {doc_path} "
                f"(segments={len(segments)})",
                flush=True,
            )

            segment_texts = [segment.text for segment in segments]
            prompt = None
            if translate_fn is None:
                prompt = _create_translation_prompt(
                    output_lang,
                    custom_prompt,
                    segment_count=len(segment_texts),
                )

            def batch_translate(batch_text: str) -> str:
                if translate_fn is not None:
                    return str(translate_fn(batch_text))
                if prompt is None:
                    raise RuntimeError("translation prompt must be initialized")
                return provider.translate_chunk(
                    text=batch_text,
                    chunk_size=len(batch_text),
                    system_prompt=prompt,
                )

            is_pro_model = resolved_model == _MODEL_ALIASES["pro"]
            planned_batches = [segment_texts]
            if is_pro_model:
                planned_batches = plan_segment_batches(
                    segment_texts,
                    max_batch_chars=_PRO_PREBATCH_MAX_CHARS,
                )
                print(
                    f"[INFO] [{doc_index}/{len(spine_docs)}] {doc_path} "
                    f"planned_batches={len(planned_batches)}",
                    flush=True,
                )

            translations: list[str] = []
            for batch_index, batch_segments in enumerate(planned_batches, start=1):
                if is_pro_model:
                    batch_chars = len(join_segments_for_batch(batch_segments))
                    print(
                        f"[INFO] [{doc_path}] Translating batch "
                        f"{batch_index}/{len(planned_batches)} "
                        f"(segments={len(batch_segments)}, chars={batch_chars})",
                        flush=True,
                    )
                translated_batch = translate_segments_with_batch_retry(
                    batch_segments,
                    translate_batch=batch_translate,
                    context_label=doc_path,
                )
                translations.extend(translated_batch)

            patched_xhtml = patch_xhtml_alternating(
                source_xhtml,
                translations,
                document_path=doc_path,
            )
            patched_bytes = patched_xhtml.encode("utf-8")
            overrides[doc_path] = patched_bytes
            translated_segments += len(segments)
            translated_docs += 1
            checkpoint_entries = _persist_checkpoint_doc(
                checkpoint_dir=checkpoint_dir,
                source_signature=source_signature,
                output_lang=output_lang,
                bilingual_style=bilingual_style,
                model=resolved_model,
                custom_prompt=custom_prompt,
                doc_path=doc_path,
                patched_xhtml_bytes=patched_bytes,
                segment_count=len(segments),
                entries=checkpoint_entries,
            )
            print(
                f"[INFO] [{doc_index}/{len(spine_docs)}] Done {doc_path}",
                flush=True,
            )

        docs: dict[str, str] = {}
        for xhtml_path in manifest_xhtml_paths:
            if xhtml_path in overrides:
                docs[xhtml_path] = overrides[xhtml_path].decode("utf-8")
            else:
                docs[xhtml_path] = _read_zip_text(source_zip, xhtml_path)

        _validate_integrity(
            model=package_model,
            existing_paths=set(source_zip.namelist()),
            docs=docs,
            allowed_broken_links=source_broken_links,
        )

    repack_epub_with_overrides(source_epub, output_epub, overrides)
    print(
        f"[INFO] Repack completed: docs={translated_docs}, segments={translated_segments}",
        flush=True,
    )
    return TranslateRoundtripResult(
        output_epub=output_epub,
        translated_segments=translated_segments,
        translated_docs=translated_docs,
    )
