from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import zipfile


def test_translatebook_help_includes_epub_baseline_mode() -> None:
    content = Path("translatebook.sh").read_text(encoding="utf-8")
    assert "--epub-baseline" in content


def test_roundtrip_script_exists() -> None:
    assert Path("08_epub_roundtrip_baseline.py").exists()


def test_translatebook_help_includes_epub_translate_roundtrip_mode() -> None:
    content = Path("translatebook.sh").read_text(encoding="utf-8")
    assert "--epub-translate-roundtrip" in content
    assert "--checkpoint-dir" in content


def test_translate_roundtrip_script_exists() -> None:
    assert Path("09_epub_translate_roundtrip.py").exists()


def _build_min_epub(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as zip_file:
        zip_file.writestr(
            "mimetype",
            "application/epub+zip",
            compress_type=zipfile.ZIP_STORED,
        )
        zip_file.writestr(
            "META-INF/container.xml",
            """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>""",
        )
        zip_file.writestr(
            "content.opf",
            """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="uid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Demo</dc:title><dc:language>en</dc:language><dc:identifier id="uid">id</dc:identifier>
    <meta name="cover" content="cover-image"/>
  </metadata>
  <manifest>
    <item id="cover-image" href="cover.jpg" media-type="image/jpeg"/>
    <item id="toc" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    <item id="c1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine toc="toc"><itemref idref="c1"/></spine>
</package>""",
        )
        zip_file.writestr(
            "chapter1.xhtml",
            "<html xmlns='http://www.w3.org/1999/xhtml'><body><h1 id='c1'>Chapter</h1></body></html>",
        )
        zip_file.writestr("toc.ncx", "<ncx></ncx>")
        zip_file.writestr("cover.jpg", "x")


def test_epub_baseline_dry_run_does_not_require_translation_dependencies() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        input_epub = Path(temp_dir) / "book.epub"
        _build_min_epub(input_epub)

        env = dict(os.environ)
        env["PATH"] = "/usr/bin:/bin"
        completed = subprocess.run(
            ["/bin/bash", "translatebook.sh", "--dry-run", "--epub-baseline", str(input_epub)],
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )

        assert completed.returncode == 0
        assert "[STEP baseline]" in completed.stdout


def test_translatebook_help_includes_workflow_flag() -> None:
    content = Path("translatebook.sh").read_text(encoding="utf-8")
    assert "--workflow" in content


def test_translatebook_help_includes_provider_flag() -> None:
    content = Path("translatebook.sh").read_text(encoding="utf-8")
    assert "--provider" in content


def test_roundtrip_script_loads_api_key_from_config() -> None:
    module = __import__("09_epub_translate_roundtrip")
    resolve_api_key_from_config = module.resolve_api_key_from_config

    config = {"gemini_api": {"api_key": "abc-123"}}
    assert resolve_api_key_from_config(config) == "abc-123"
    assert resolve_api_key_from_config({}) is None


def test_roundtrip_script_loader_prefers_workspace_config_over_example(tmp_path: Path) -> None:
    module = __import__("09_epub_translate_roundtrip")
    load_runtime_config = module.load_runtime_config

    script_dir = Path(module.__file__).resolve().parent
    workspace_config = script_dir / "config" / "config.json"
    backup = workspace_config.read_text(encoding="utf-8") if workspace_config.exists() else None

    try:
        workspace_config.write_text(
            '{"gemini_api":{"api_key":"workspace-key","model":"gemini-2.5-flash"}}',
            encoding="utf-8",
        )
        loaded = load_runtime_config()
        assert isinstance(loaded, dict)
        gemini_api = loaded.get("gemini_api")
        assert isinstance(gemini_api, dict)
        assert gemini_api.get("api_key") == "workspace-key"
    finally:
        if backup is None:
            workspace_config.unlink(missing_ok=True)
        else:
            workspace_config.write_text(backup, encoding="utf-8")


def test_roundtrip_script_resolves_epub_resilience_config() -> None:
    module = __import__("09_epub_translate_roundtrip")
    resolve_epub_resilience_config = module.resolve_epub_resilience_config

    config = {
        "epub_resilience": {
            "rate_limit_backoff_seconds": [12, 34],
            "timeout_backoff_seconds": [9],
            "transient_backoff_seconds": [7],
            "max_split_depth": 5,
            "doc_failure_budget": 2,
            "cli_api_fallback_enabled": True,
            "pro_timeout_seconds": 500,
            "non_pro_timeout_seconds": 222,
            "failed_docs_path": "./tmp/failed-docs.json",
        }
    }
    resolved = resolve_epub_resilience_config(config)

    assert resolved["rate_limit_backoff_seconds"] == (12, 34)
    assert resolved["timeout_backoff_seconds"] == (9,)
    assert resolved["transient_backoff_seconds"] == (7,)
    assert resolved["max_split_depth"] == 5
    assert resolved["doc_failure_budget"] == 2
    assert resolved["cli_api_fallback_enabled"] is True
    assert resolved["pro_timeout_seconds"] == 500
    assert resolved["non_pro_timeout_seconds"] == 222
    assert str(resolved["failed_docs_path"]).endswith("/tmp/failed-docs.json")


def test_roundtrip_script_invalid_resilience_backoff_raises() -> None:
    module = __import__("09_epub_translate_roundtrip")
    resolve_epub_resilience_config = module.resolve_epub_resilience_config

    config = {"epub_resilience": {"timeout_backoff_seconds": [10, 0]}}
    try:
        resolve_epub_resilience_config(config)
    except ValueError as exc:
        assert "timeout_backoff_seconds" in str(exc)
    else:
        raise AssertionError("expected ValueError for invalid timeout_backoff_seconds")


def test_epub_default_dry_run_uses_epub_workflow() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        input_epub = Path(temp_dir) / "book.epub"
        _build_min_epub(input_epub)

        completed = subprocess.run(
            ["/bin/bash", "translatebook.sh", "--dry-run", str(input_epub)],
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            text=True,
            env=dict(os.environ),
            check=False,
        )

        assert completed.returncode == 0
        assert "Resolved workflow: epub" in completed.stdout
        assert "[STEP workflow-epub]" in completed.stdout
