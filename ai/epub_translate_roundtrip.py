from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import zipfile

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

TranslateFn = callable


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


def _create_translation_prompt(output_lang: str, custom_prompt: str | None) -> str:
    language_name = _get_language_name(output_lang)
    base_prompt = (
        "Translate the following EPUB text segment to "
        f"{language_name}. Output only translated text without explanations."
    )
    if custom_prompt:
        return f"{base_prompt}\n\nADDITIONAL INSTRUCTIONS:\n{custom_prompt}"
    return base_prompt


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
    translate_fn=None,
) -> TranslateRoundtripResult:
    if bilingual_style != "alternating":
        raise ValueError("Only 'alternating' bilingual style is supported")

    package_model = load_epub_package(source_epub)
    prompt = _create_translation_prompt(output_lang, custom_prompt)
    provider = GeminiProvider(model=model)
    overrides: dict[str, bytes] = {}
    translated_segments = 0
    translated_docs = 0

    with zipfile.ZipFile(source_epub, "r") as source_zip:
        for doc_path in _resolve_spine_xhtml_paths(package_model):
            source_xhtml = _read_zip_text(source_zip, doc_path)
            segments = extract_translatable_segments(source_xhtml)
            if not segments:
                continue

            translations: list[str] = []
            for segment in segments:
                if translate_fn is not None:
                    translated = str(translate_fn(segment.text))
                else:
                    translated = provider.translate_chunk(
                        text=segment.text,
                        chunk_size=len(segment.text),
                        system_prompt=prompt,
                    )
                translations.append(translated)

            patched_xhtml = patch_xhtml_alternating(source_xhtml, translations)
            overrides[doc_path] = patched_xhtml.encode("utf-8")
            translated_segments += len(segments)
            translated_docs += 1

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
    return TranslateRoundtripResult(
        output_epub=output_epub,
        translated_segments=translated_segments,
        translated_docs=translated_docs,
    )
