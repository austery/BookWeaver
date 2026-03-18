from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import zipfile
from typing import Callable

from ai.epub_package import (
    EpubPackageModel,
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

TranslateFn = Callable[[str], str]
_MODEL_ALIASES = {
    "pro": "gemini-3-pro-preview",
    "flash": "gemini-2.5-flash",
    "lite": "gemini-2.5-flash-lite",
}
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


def _get_language_name(lang_code: str) -> str:
    language_map = {
        "zh": "Chinese",
        "en": "English",
        "ja": "Japanese",
        "ko": "Korean",
        "fr": "French",
        "de": "German",
        "es": "Spanish",
        "it": "Italian",
        "pt": "Portuguese",
        "ru": "Russian",
    }
    return language_map.get(lang_code.lower(), lang_code)


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


def join_segments_for_batch(segments: list[str]) -> str:
    if not segments:
        return ""
    if len(segments) == 1:
        return segments[0]
    return _BATCH_SEPARATOR.join(segments)


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
    translated_batch = str(translate_batch(batch_text))

    try:
        return split_batch_translation(translated_batch, expected_count=expected_count)
    except ValueError as exc:
        if expected_count == 1:
            raise RuntimeError(
                f"Batch translation alignment failed at minimal granularity for {context_label}: {exc}"
            ) from exc

        split_index = expected_count // 2
        print(
            f"[WARN] [{context_label}] Batch output mismatch at depth={retry_depth}, "
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


def _read_zip_text(zip_file: zipfile.ZipFile, path: str) -> str:
    raw = zip_file.read(path)
    return raw.decode("utf-8")


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
) -> None:
    errors: list[str] = []
    errors.extend(validate_package_structure(model).errors)

    manifest_paths = _resolve_manifest_paths(model)
    missing_assets = validate_manifest_assets(manifest_paths, existing_paths).missing_paths
    for path in missing_assets:
        errors.append(f"missing manifest asset: {path}")

    broken_links = validate_fragment_links(docs).broken_links
    for link in broken_links:
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
) -> TranslateRoundtripResult:
    if bilingual_style != "alternating":
        raise ValueError("Only 'alternating' bilingual style is supported")

    resolved_model = _resolve_model_name(model)
    package_model = load_epub_package(source_epub)
    provider = GeminiProvider(model=resolved_model)
    overrides: dict[str, bytes] = {}
    translated_segments = 0
    translated_docs = 0
    spine_docs = _resolve_spine_xhtml_paths(package_model)
    print(
        f"[INFO] Loaded package: {source_epub.name}, "
        f"spine docs={len(spine_docs)}, model={resolved_model}",
        flush=True,
    )

    with zipfile.ZipFile(source_epub, "r") as source_zip:
        for doc_index, doc_path in enumerate(spine_docs, start=1):
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

            translations = translate_segments_with_batch_retry(
                segment_texts,
                translate_batch=batch_translate,
                context_label=doc_path,
            )

            patched_xhtml = patch_xhtml_alternating(source_xhtml, translations)
            overrides[doc_path] = patched_xhtml.encode("utf-8")
            translated_segments += len(segments)
            translated_docs += 1
            print(
                f"[INFO] [{doc_index}/{len(spine_docs)}] Done {doc_path}",
                flush=True,
            )

        docs: dict[str, str] = {}
        for xhtml_path in _resolve_manifest_xhtml_paths(package_model):
            if xhtml_path in overrides:
                docs[xhtml_path] = overrides[xhtml_path].decode("utf-8")
            else:
                docs[xhtml_path] = _read_zip_text(source_zip, xhtml_path)

        _validate_integrity(
            model=package_model,
            existing_paths=set(source_zip.namelist()),
            docs=docs,
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
