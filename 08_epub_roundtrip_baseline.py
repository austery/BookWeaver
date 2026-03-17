#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path
import zipfile

from ai.epub_package import (
    EpubPackageModel,
    load_epub_package,
    repack_epub,
    resolve_opf_href,
    validate_fragment_links,
    validate_manifest_assets,
    validate_package_structure,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Roundtrip EPUB baseline mode")
    parser.add_argument("input_epub", help="Source EPUB path")
    parser.add_argument("--output", required=True, help="Output EPUB path")
    return parser.parse_args()


def _collect_manifest_paths(model: EpubPackageModel) -> list[str]:
    return [resolve_opf_href(model.opf_path, item.href) for item in model.manifest_items.values()]


def _collect_xhtml_docs(source_epub: Path, model: EpubPackageModel) -> dict[str, str]:
    docs: dict[str, str] = {}
    with zipfile.ZipFile(source_epub, "r") as zip_file:
        for item in model.manifest_items.values():
            if item.media_type != "application/xhtml+xml":
                continue
            doc_path = resolve_opf_href(model.opf_path, item.href)
            if doc_path not in zip_file.namelist():
                continue
            docs[doc_path] = zip_file.read(doc_path).decode("utf-8")
    return docs


def _validate_baseline_integrity(source_epub: Path, model: EpubPackageModel) -> None:
    errors = list(validate_package_structure(model).errors)
    with zipfile.ZipFile(source_epub, "r") as zip_file:
        existing_paths = set(zip_file.namelist())

    manifest_paths = _collect_manifest_paths(model)
    asset_report = validate_manifest_assets(manifest_paths, existing_paths)
    for missing_path in asset_report.missing_paths:
        errors.append(f"missing manifest asset: {missing_path}")

    docs = _collect_xhtml_docs(source_epub, model)
    link_report = validate_fragment_links(docs)
    for broken_link in link_report.broken_links:
        errors.append(f"broken fragment link: {broken_link}")

    if errors:
        for error in errors:
            print(f"[ERROR] {error}")
        raise SystemExit(1)


def main() -> None:
    args = parse_arguments()
    source_epub = Path(args.input_epub).expanduser().resolve()
    output_epub = Path(args.output).expanduser().resolve()

    package_model = load_epub_package(source_epub)
    _validate_baseline_integrity(source_epub, package_model)
    print(
        f"OPF: {package_model.opf_path}, cover: {package_model.cover_item_id}, "
        f"spine: {len(package_model.spine_itemrefs)} items"
    )
    repack_epub(source_epub, output_epub)
    print(f"Roundtrip EPUB generated: {output_epub}")


if __name__ == "__main__":
    main()
