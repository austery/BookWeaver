from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import posixpath
import re
import zipfile
import xml.etree.ElementTree as ET

_CONTAINER_NS = {"container": "urn:oasis:names:tc:opendocument:xmlns:container"}
_OPF_NS = {"opf": "http://www.idpf.org/2007/opf"}
_XHTML_NS = "http://www.w3.org/1999/xhtml"
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


@dataclass(frozen=True, slots=True)
class TranslatableSegment:
    text: str
    block_path: tuple[int, ...]
    tag_name: str


_SKIP_TEXT_TAGS = {"script", "style"}
_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_HEADING_CLASS_HINTS = ("head", "title", "subhead")
_STRUCTURAL_CONTAINER_TAGS = {
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
    "caption",
    "ul",
    "ol",
    "dl",
    "img",
    "svg",
    "nav",
}
_EMPHASIS_TAGS = {"b", "strong"}
_EMPHASIS_CLASS_HINTS = ("bold",)
_MAX_HEADING_LIKE_DIV_TEXT_LEN = 120
_TOC_DOC_HINTS = ("toc", "contents")
_TOC_ROLE_HINTS = ("doc-toc",)
_STYLE_ELEMENT_ID = "bookweaver-bilingual-style"
_TRANSLATION_CLASS = "bw-translation"
_CAPTION_COMPAT_CSS = (
    ".bw-translation { margin-top: 0.2em; }\n"
    "#sbo-rt-content table caption,\n"
    "#sbo-rt-content .table-title {\n"
    "  writing-mode: horizontal-tb !important;\n"
    "  -webkit-writing-mode: horizontal-tb !important;\n"
    "  text-orientation: mixed !important;\n"
    "  transform: none !important;\n"
    "  display: table-caption !important;\n"
    "}"
)
_BLOCK_TAGS = {"p", "li", "blockquote", "dd", "div"}

ET.register_namespace("", _XHTML_NS)


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _find_body(root: ET.Element) -> ET.Element | None:
    for node in root.iter():
        if _local_name(node.tag) == "body":
            return node
    return None


def _find_head(root: ET.Element) -> ET.Element | None:
    for node in root.iter():
        if _local_name(node.tag) == "head":
            return node
    return None


def _tag_namespace(tag: str) -> str | None:
    if tag.startswith("{") and "}" in tag:
        return tag[1:].split("}", 1)[0]
    return None


def _qualified_tag(local_tag: str, namespace: str | None) -> str:
    if namespace:
        return f"{{{namespace}}}{local_tag}"
    return local_tag


def _has_toc_filename_hint(document_path: str | None) -> bool:
    if not document_path:
        return False
    lowered = posixpath.basename(document_path).lower()
    return any(hint in lowered for hint in _TOC_DOC_HINTS)


def _attribute_tokens(node: ET.Element, attr_local_name: str) -> set[str]:
    tokens: set[str] = set()
    for key, value in node.attrib.items():
        if _local_name(key).lower() == attr_local_name:
            tokens.update(value.lower().split())
    return tokens


def _is_toc_nav_node(node: ET.Element) -> bool:
    if _local_name(node.tag).lower() != "nav":
        return False
    if "toc" in _attribute_tokens(node, "type"):
        return True
    role_tokens = _attribute_tokens(node, "role")
    return any(hint in role_tokens for hint in _TOC_ROLE_HINTS)


def _is_toc_document(document_path: str | None) -> bool:
    return _has_toc_filename_hint(document_path)


def _is_heading_like_node(node: ET.Element) -> bool:
    tag_name = _local_name(node.tag).lower()
    if tag_name in _HEADING_TAGS:
        return True

    class_name = (node.get("class") or "").lower()
    if any(hint in class_name for hint in _HEADING_CLASS_HINTS):
        return True

    if tag_name != "div":
        return False

    return _is_emphasized_heading_div(node)


def _has_structural_container_descendant(node: ET.Element) -> bool:
    return any(
        descendant is not node and _local_name(descendant.tag).lower() in _STRUCTURAL_CONTAINER_TAGS
        for descendant in node.iter()
    )


def _has_toc_nav_ancestor(
    node: ET.Element,
    parent_map: dict[ET.Element, ET.Element],
) -> bool:
    current: ET.Element | None = node
    while current is not None:
        if _is_toc_nav_node(current):
            return True
        current = parent_map.get(current)
    return False


def _node_has_emphasis_signal(node: ET.Element) -> bool:
    """Return whether this node itself carries an emphasis signal."""
    tag = _local_name(node.tag).lower()
    if tag in _EMPHASIS_TAGS:
        return True
    class_name = (node.get("class") or "").lower()
    return any(hint in class_name for hint in _EMPHASIS_CLASS_HINTS)


def _subtree_has_emphasis_signal(node: ET.Element) -> bool:
    return any(_node_has_emphasis_signal(descendant) for descendant in node.iter())


def _has_only_inline_descendants(node: ET.Element) -> bool:
    disallowed_tags = _BLOCK_TAGS | _STRUCTURAL_CONTAINER_TAGS | _HEADING_TAGS
    return all(
        descendant is node or _local_name(descendant.tag).lower() not in disallowed_tags
        for descendant in node.iter()
    )


def _is_heading_suffix_text(text: str) -> bool:
    compact = "".join(ch for ch in text if not ch.isspace())
    if not compact:
        return True
    if not any(ch.isalnum() for ch in compact):
        return True
    return compact.upper() == compact


def _is_emphasized_heading_div(node: ET.Element) -> bool:
    text = _normalize_visible_text(node)
    if not text or len(text) > _MAX_HEADING_LIKE_DIV_TEXT_LEN:
        return False
    if not _subtree_has_emphasis_signal(node):
        return False
    if not _has_only_inline_descendants(node):
        return False
    return _is_heading_suffix_text(_normalize_non_emphasized_text(node))


def _should_render_translation(*, block_node: ET.Element, is_toc_document: bool) -> bool:
    if is_toc_document:
        return False
    return not _is_heading_like_node(block_node)


def _determine_translation_sibling_tag(parent: ET.Element) -> str:
    parent_tag = _local_name(parent.tag).lower()
    if parent_tag == "dl":
        return "dd"
    return "p"


def _set_translation_text(elem: ET.Element, translation: str, namespace: str) -> None:
    """Set translated text on an element, preserving \\n as <br/> elements.

    When the source block contains <br/> tags (e.g. Kindle index entries), the
    extracted text uses \\n as line-break markers. Plain-text assignment loses
    those breaks because HTML collapses whitespace. Convert \\n back to <br/>
    so the hierarchical index structure is visible in the translated output.
    """
    if "\n" not in translation:
        elem.text = translation
        return

    lines = translation.split("\n")
    elem.text = lines[0]
    for line in lines[1:]:
        br = ET.SubElement(elem, _qualified_tag("br", namespace))
        br.tail = line


def _insert_translation_block(
    *,
    block_node: ET.Element,
    translation: str,
    parent_map: dict[ET.Element, ET.Element],
) -> None:
    namespace = _tag_namespace(block_node.tag)
    parent = parent_map.get(block_node)
    if parent is None:
        return

    parent_tag = _local_name(parent.tag).lower()
    if parent_tag in {"ul", "ol"}:
        # Nest translation inside the source <li> so <ol> numbering is
        # not disrupted (inserting a sibling <li> would double the count).
        translated_block = ET.SubElement(
            block_node,
            _qualified_tag("p", namespace),
            attrib={"class": _TRANSLATION_CLASS},
        )
        _set_translation_text(translated_block, translation, namespace)
        return

    sibling_tag = _determine_translation_sibling_tag(parent)
    translated_block = ET.Element(
        _qualified_tag(sibling_tag, namespace),
        attrib={"class": _TRANSLATION_CLASS},
    )
    _set_translation_text(translated_block, translation, namespace)

    children = list(parent)
    block_index = children.index(block_node)
    parent.insert(block_index + 1, translated_block)


def _ensure_translation_style(root: ET.Element) -> None:
    head = _find_head(root)
    if head is None:
        return
    for node in head:
        if _local_name(node.tag) == "style" and node.get("id") == _STYLE_ELEMENT_ID:
            return

    namespace = _tag_namespace(head.tag)
    style = ET.Element(
        _qualified_tag("style", namespace),
        attrib={"id": _STYLE_ELEMENT_ID, "type": "text/css"},
    )
    style.text = _CAPTION_COMPAT_CSS
    head.append(style)


def _build_parent_map(body: ET.Element) -> dict[ET.Element, ET.Element]:
    return {child: parent for parent in body.iter() for child in list(parent)}


def _has_skip_ancestor(node: ET.Element, parent_map: dict[ET.Element, ET.Element]) -> bool:
    current = parent_map.get(node)
    while current is not None:
        if _local_name(current.tag).lower() in _SKIP_TEXT_TAGS:
            return True
        current = parent_map.get(current)
    return False


def _append_visible_text_parts(node: ET.Element, parts: list[str]) -> None:
    if node.text:
        parts.append(node.text)

    for child in node:
        if _local_name(child.tag).lower() == "br":
            parts.append("\n")
            if child.tail:
                parts.append(child.tail.lstrip())
        else:
            _append_visible_text_parts(child, parts)
            if child.tail:
                parts.append(child.tail)


def _normalize_text_parts(parts: list[str]) -> str:
    lines = "".join(parts).split("\n")

    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()

    normalized_lines: list[str] = []
    for line in lines:
        words = line.split()
        normalized_lines.append(" ".join(words) if words else "")
    return "\n".join(normalized_lines)


def _append_non_emphasized_text_parts(
    node: ET.Element,
    parts: list[str],
    *,
    inside_emphasis: bool = False,
) -> None:
    current_inside_emphasis = inside_emphasis or _node_has_emphasis_signal(node)
    if not current_inside_emphasis and node.text:
        parts.append(node.text)

    for child in node:
        if _local_name(child.tag).lower() == "br":
            if not current_inside_emphasis:
                parts.append("\n")
                if child.tail:
                    parts.append(child.tail.lstrip())
            continue

        _append_non_emphasized_text_parts(
            child,
            parts,
            inside_emphasis=current_inside_emphasis,
        )
        if not current_inside_emphasis and child.tail:
            parts.append(child.tail)


def _normalize_non_emphasized_text(node: ET.Element) -> str:
    parts: list[str] = []
    _append_non_emphasized_text_parts(node, parts)
    return _normalize_text_parts(parts)


def _normalize_visible_text(node: ET.Element) -> str:
    parts: list[str] = []
    _append_visible_text_parts(node, parts)
    return _normalize_text_parts(parts)


def _has_translatable_block_descendant(node: ET.Element) -> bool:
    for descendant in node.iter():
        if descendant is node:
            continue
        tag = _local_name(descendant.tag).lower()
        if tag not in _BLOCK_TAGS:
            continue
        if _normalize_visible_text(descendant):
            return True
    return False


def _node_path_from_body(
    *,
    body: ET.Element,
    node: ET.Element,
    parent_map: dict[ET.Element, ET.Element],
) -> tuple[int, ...]:
    path: list[int] = []
    current = node
    while current is not body:
        parent = parent_map.get(current)
        if parent is None:
            raise ValueError("node is not inside body")
        children = list(parent)
        path.append(children.index(current))
        current = parent
    path.reverse()
    return tuple(path)


def _resolve_node_by_path(body: ET.Element, path: tuple[int, ...]) -> ET.Element | None:
    current = body
    for index in path:
        children = list(current)
        if index < 0 or index >= len(children):
            return None
        current = children[index]
    return current


def _collect_translatable_block_segments(
    body: ET.Element,
    *,
    is_toc_document: bool = False,
) -> list[TranslatableSegment]:
    if is_toc_document:
        return []

    parent_map = _build_parent_map(body)
    segments: list[TranslatableSegment] = []
    for node in body.iter():
        tag_name = _local_name(node.tag).lower()
        if tag_name not in _BLOCK_TAGS:
            continue
        if _has_skip_ancestor(node, parent_map):
            continue
        if _has_toc_nav_ancestor(node, parent_map):
            continue
        if _is_heading_like_node(node):
            continue
        if tag_name == "div" and _has_structural_container_descendant(node):
            continue
        if _has_translatable_block_descendant(node):
            continue
        text = _normalize_visible_text(node)
        if not text:
            continue
        segments.append(
            TranslatableSegment(
                text=text,
                block_path=_node_path_from_body(body=body, node=node, parent_map=parent_map),
                tag_name=tag_name,
            )
        )
    return segments


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


def repack_epub_with_overrides(
    source_epub: Path,
    output_epub: Path,
    file_overrides: dict[str, bytes] | None = None,
) -> None:
    overrides = file_overrides or {}
    with zipfile.ZipFile(source_epub, "r") as source_zip:
        infos = source_zip.infolist()
        known_paths = {info.filename for info in infos}
        unknown_overrides = sorted(path for path in overrides if path not in known_paths)
        if unknown_overrides:
            raise ValueError(
                f"Override paths not found in source EPUB: {', '.join(unknown_overrides)}"
            )

        mimetype_info = next((info for info in infos if info.filename == "mimetype"), None)
        if mimetype_info is None:
            raise ValueError("EPUB missing required file: mimetype")
        remaining_infos = [info for info in infos if info.filename != "mimetype"]

        output_epub.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output_epub, "w") as output_zip:
            mimetype_bytes = overrides.get(
                mimetype_info.filename, source_zip.read(mimetype_info.filename)
            )
            cloned = _clone_zip_info(mimetype_info)
            cloned.compress_type = zipfile.ZIP_STORED
            output_zip.writestr(cloned, mimetype_bytes)

            for info in remaining_infos:
                content = overrides.get(info.filename, source_zip.read(info.filename))
                output_zip.writestr(_clone_zip_info(info), content)


def repack_epub(source_epub: Path, output_epub: Path) -> None:
    repack_epub_with_overrides(source_epub, output_epub, file_overrides=None)


def validate_package_structure(model: EpubPackageModel) -> PackageValidationReport:
    errors: list[str] = []
    manifest_item_ids = set(model.manifest_items)
    manifest_hrefs = {item.href for item in model.manifest_items.values()}

    if (
        model.cover_item_id
        and model.cover_item_id not in manifest_item_ids
        and model.cover_item_id not in manifest_hrefs
    ):
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


def extract_translatable_segments(
    xhtml: str, document_path: str | None = None
) -> list[TranslatableSegment]:
    root = ET.fromstring(xhtml)
    body = _find_body(root)
    if body is None:
        return []
    is_toc_document = _is_toc_document(document_path)
    return _collect_translatable_block_segments(body, is_toc_document=is_toc_document)


def patch_xhtml_alternating(
    xhtml: str,
    translations: list[str],
    *,
    document_path: str | None = None,
) -> str:
    root = ET.fromstring(xhtml)
    body = _find_body(root)
    if body is None:
        if translations:
            raise ValueError("translation count does not match translatable segments")
        return xhtml

    is_toc_document = _is_toc_document(document_path)
    segments = _collect_translatable_block_segments(body, is_toc_document=is_toc_document)
    if len(segments) != len(translations):
        raise ValueError(
            f"translation count mismatch: expected {len(segments)}, got {len(translations)}"
        )

    parent_map = _build_parent_map(body)
    block_nodes: list[ET.Element] = []
    for segment in segments:
        block_node = _resolve_node_by_path(body, segment.block_path)
        if block_node is None:
            raise ValueError("translation block anchor not found")
        block_nodes.append(block_node)

    has_rendered_translation = False
    for block_node, translation in zip(block_nodes, translations, strict=True):
        if not _should_render_translation(
            block_node=block_node,
            is_toc_document=is_toc_document,
        ):
            continue

        _insert_translation_block(
            block_node=block_node,
            translation=translation,
            parent_map=parent_map,
        )
        has_rendered_translation = True

    if has_rendered_translation:
        _ensure_translation_style(root)

    return ET.tostring(root, encoding="unicode")
