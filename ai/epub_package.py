from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import posixpath
import re
import zipfile
import xml.etree.ElementTree as ET

_CONTAINER_NS = {"container": "urn:oasis:names:tc:opendocument:xmlns:container"}
_OPF_NS = {"opf": "http://www.idpf.org/2007/opf"}
_ID_PATTERN = re.compile(r"""id=["']([^"']+)["']""")
_HREF_PATTERN = re.compile(r"""href=["']([^"']+)["']""")
_EXTERNAL_SCHEMES = ("http://", "https://", "mailto:", "tel:", "javascript:")


@dataclass(frozen=True, slots=True)
class EpubPackageModel:
    epub_path: Path
    opf_path: str
    cover_item_id: str | None
    spine_itemrefs: list[str]
    manifest_items: dict[str, ManifestItem]
    toc_item_id: str | None


@dataclass(frozen=True, slots=True)
class LinkReport:
    broken_count: int
    broken_links: list[str]


@dataclass(frozen=True, slots=True)
class AssetReport:
    missing_paths: list[str]


@dataclass(frozen=True, slots=True)
class ManifestItem:
    id: str
    href: str
    media_type: str | None


@dataclass(frozen=True, slots=True)
class PackageValidationReport:
    errors: list[str]


def _clone_zip_info(info: zipfile.ZipInfo) -> zipfile.ZipInfo:
    clone = zipfile.ZipInfo(filename=info.filename, date_time=info.date_time)
    clone.compress_type = info.compress_type
    clone.comment = info.comment
    clone.extra = info.extra
    clone.create_system = info.create_system
    clone.create_version = info.create_version
    clone.extract_version = info.extract_version
    clone.reserved = info.reserved
    clone.flag_bits = info.flag_bits
    clone.volume = info.volume
    clone.internal_attr = info.internal_attr
    clone.external_attr = info.external_attr
    return clone


def _read_zip_text(zip_file: zipfile.ZipFile, path: str) -> str:
    try:
        raw_bytes = zip_file.read(path)
    except KeyError as exc:
        raise ValueError(f"EPUB missing required file: {path}") from exc
    try:
        return raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"EPUB file is not valid UTF-8 XML: {path}") from exc


def _resolve_opf_path(zip_file: zipfile.ZipFile) -> str:
    container_xml = _read_zip_text(zip_file, "META-INF/container.xml")
    container_root = ET.fromstring(container_xml)
    rootfile = container_root.find(".//container:rootfile", _CONTAINER_NS)
    if rootfile is None:
        raise ValueError("container.xml does not contain a rootfile entry")
    opf_path = rootfile.get("full-path")
    if not opf_path:
        raise ValueError("container.xml rootfile is missing full-path")
    return opf_path


def _extract_cover_item_id(opf_root: ET.Element) -> str | None:
    metadata = opf_root.find("opf:metadata", _OPF_NS)
    if metadata is None:
        return None

    for meta in metadata.findall("opf:meta", _OPF_NS):
        if meta.get("name") == "cover":
            return meta.get("content")

    return None


def _extract_manifest_items(opf_root: ET.Element) -> dict[str, ManifestItem]:
    manifest = opf_root.find("opf:manifest", _OPF_NS)
    if manifest is None:
        return {}

    manifest_items: dict[str, ManifestItem] = {}
    for item in manifest.findall("opf:item", _OPF_NS):
        item_id = item.get("id")
        href = item.get("href")
        if not item_id or not href:
            continue
        manifest_items[item_id] = ManifestItem(
            id=item_id,
            href=href,
            media_type=item.get("media-type"),
        )
    return manifest_items


def _extract_spine_itemrefs(opf_root: ET.Element) -> list[str]:
    spine = opf_root.find("opf:spine", _OPF_NS)
    if spine is None:
        return []

    spine_itemrefs: list[str] = []
    for itemref in spine.findall("opf:itemref", _OPF_NS):
        idref = itemref.get("idref")
        if idref:
            spine_itemrefs.append(idref)
    return spine_itemrefs


def _extract_toc_item_id(opf_root: ET.Element) -> str | None:
    spine = opf_root.find("opf:spine", _OPF_NS)
    if spine is None:
        return None
    return spine.get("toc")


def load_epub_package(epub_path: Path) -> EpubPackageModel:
    with zipfile.ZipFile(epub_path, "r") as zip_file:
        opf_path = _resolve_opf_path(zip_file)
        opf_xml = _read_zip_text(zip_file, opf_path)
        opf_root = ET.fromstring(opf_xml)

    cover_item_id = _extract_cover_item_id(opf_root)
    spine_itemrefs = _extract_spine_itemrefs(opf_root)
    manifest_items = _extract_manifest_items(opf_root)
    toc_item_id = _extract_toc_item_id(opf_root)

    return EpubPackageModel(
        epub_path=epub_path,
        opf_path=opf_path,
        cover_item_id=cover_item_id,
        spine_itemrefs=spine_itemrefs,
        manifest_items=manifest_items,
        toc_item_id=toc_item_id,
    )


def repack_epub(source_epub: Path, output_epub: Path) -> None:
    with zipfile.ZipFile(source_epub, "r") as source_zip:
        infos = source_zip.infolist()
        mimetype_info = next((info for info in infos if info.filename == "mimetype"), None)
        if mimetype_info is None:
            raise ValueError("EPUB missing required file: mimetype")
        remaining_infos = [info for info in infos if info.filename != "mimetype"]

        output_epub.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output_epub, "w") as output_zip:
            if mimetype_info is not None:
                mimetype_bytes = source_zip.read(mimetype_info.filename)
                cloned = _clone_zip_info(mimetype_info)
                cloned.compress_type = zipfile.ZIP_STORED
                output_zip.writestr(cloned, mimetype_bytes)

            for info in remaining_infos:
                output_zip.writestr(_clone_zip_info(info), source_zip.read(info.filename))


def validate_package_structure(model: EpubPackageModel) -> PackageValidationReport:
    errors: list[str] = []
    manifest_item_ids = set(model.manifest_items.keys())

    if model.cover_item_id and model.cover_item_id not in manifest_item_ids:
        errors.append(f"cover item id not found in manifest: {model.cover_item_id}")

    if model.toc_item_id and model.toc_item_id not in manifest_item_ids:
        errors.append(f"toc item id not found in manifest: {model.toc_item_id}")

    for itemref in model.spine_itemrefs:
        if itemref not in manifest_item_ids:
            errors.append(f"spine itemref not found in manifest: {itemref}")

    return PackageValidationReport(errors=errors)


def _normalize_target_doc(current_doc: str, href_target: str) -> str:
    base, _, _fragment = href_target.partition("#")
    if not base:
        return current_doc
    current_dir = posixpath.dirname(current_doc)
    return posixpath.normpath(posixpath.join(current_dir, base))


def validate_fragment_links(docs: dict[str, str]) -> LinkReport:
    broken_links: list[str] = []
    ids_by_doc: dict[str, set[str]] = {
        doc_path: {match.group(1) for match in _ID_PATTERN.finditer(html)}
        for doc_path, html in docs.items()
    }

    for doc_path, html in docs.items():
        for match in _HREF_PATTERN.finditer(html):
            href_target = match.group(1)
            if "#" not in href_target:
                continue
            if href_target.startswith(_EXTERNAL_SCHEMES):
                continue

            _, _, fragment = href_target.partition("#")
            if not fragment:
                continue

            target_doc = _normalize_target_doc(doc_path, href_target)
            target_ids = ids_by_doc.get(target_doc)
            if target_ids is None or fragment not in target_ids:
                broken_links.append(f"{doc_path}:{href_target}")

    return LinkReport(broken_count=len(broken_links), broken_links=broken_links)


def validate_manifest_assets(manifest_paths: list[str], existing_paths: set[str]) -> AssetReport:
    missing_paths = [path for path in manifest_paths if path not in existing_paths]
    return AssetReport(missing_paths=missing_paths)


def resolve_opf_href(opf_path: str, href: str) -> str:
    opf_dir = PurePosixPath(opf_path).parent
    if str(opf_dir) == ".":
        return posixpath.normpath(href)
    return posixpath.normpath(posixpath.join(str(opf_dir), href))
