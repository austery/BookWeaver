from __future__ import annotations


def test_detects_broken_fragment_links_in_spine_docs() -> None:
    from ai.epub_package import validate_fragment_links

    html = "<html><body><a href='#missing'>go</a><h1 id='ok'>ok</h1></body></html>"
    report = validate_fragment_links({"chapter1.xhtml": html})
    assert report.broken_count == 1


def test_detects_missing_manifest_assets() -> None:
    from ai.epub_package import validate_manifest_assets

    manifest = ["images/a.jpg", "styles/main.css"]
    existing = {"styles/main.css"}
    report = validate_manifest_assets(manifest, existing)
    assert "images/a.jpg" in report.missing_paths


def test_detects_broken_cross_document_fragment_links() -> None:
    from ai.epub_package import validate_fragment_links

    docs = {
        "text/ch1.xhtml": "<html><body><a href='ch2.xhtml#missing'>go</a></body></html>",
        "text/ch2.xhtml": "<html><body><h1 id='ok'>ok</h1></body></html>",
    }
    report = validate_fragment_links(docs)
    assert report.broken_count == 1
