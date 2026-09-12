"""Verify built artifacts and the installed console command without model execution.

Dependency packages come from the lockfile-synced caller environment. Only the
wheel under test supplies BookWeaver; the child asserts its installed location.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig
import tarfile
import tempfile
import zipfile


def run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(f"Command failed: {command[0]}\n{result.stdout}\n{result.stderr}")
    return result.stdout.strip()


def make_source(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr(
            "META-INF/container.xml",
            '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="content.opf"/></rootfiles></container>',
        )
        archive.writestr(
            "content.opf",
            '<package xmlns="http://www.idpf.org/2007/opf" version="3.0"><metadata/><manifest><item id="bib" href="bib.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="bib"/></spine></package>',
        )
        archive.writestr(
            "bib.xhtml",
            '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>References</title></head><body><h1>Bibliography</h1><p>Example Author. Example Source.</p></body></html>',
        )


def verify(wheel: Path, sdist: Path, root: Path) -> None:
    canonical = (Path(__file__).resolve().parents[1] / "ai/config_schema.json").read_bytes()
    with zipfile.ZipFile(wheel) as archive:
        assert archive.read("ai/config_schema.json") == canonical
    with tarfile.open(sdist) as archive:
        members = [m for m in archive.getmembers() if m.name.endswith("/ai/config_schema.json")]
        assert len(members) == 1
        stream = archive.extractfile(members[0])
        assert stream is not None and stream.read() == canonical

    uv = shutil.which("uv")
    assert uv is not None
    environment = root / "installed"
    run([uv, "venv", "--python", sys.executable, str(environment)], cwd=root)
    python = environment / "bin/python"
    run(
        [uv, "pip", "install", "--python", str(python), "--no-deps", "--no-index", str(wheel)],
        cwd=root,
    )
    site = Path(
        run(
            [str(python), "-I", "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
            cwd=root,
        )
    )
    # A .pth path entry does not execute the caller's editable-install .pth files.
    # The installed package location assertion below prevents source-tree fallback.
    (site / "smoke_dependencies.pth").write_text(sysconfig.get_path("purelib") + "\n")
    home, working = root / "user", root / "elsewhere"
    home.mkdir()
    working.mkdir()
    marker = root / "provider-attempted"
    (site / "sitecustomize.py").write_text(
        "from pathlib import Path\nimport sys\n"
        f"Path.home = classmethod(lambda cls: Path({str(home)!r}))\n"
        "import ai\n"
        "if not Path(ai.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()):\n"
        "    raise RuntimeError('BookWeaver was not imported from the installed wheel')\n"
        "from ai.runtime_factory import DefaultProviderFactory\n"
        "def reject_provider(*args, **kwargs):\n"
        f"    Path({str(marker)!r}).write_text('attempted')\n"
        "    raise AssertionError('Installed smoke must never construct a Provider')\n"
        "DefaultProviderFactory.create = reject_provider\n"
    )
    # A startup hook error is normally printed and ignored by Python; prove the
    # hook ran and that the package is installed again inside the child command.
    probe = (
        "from pathlib import Path; import sys, ai; "
        f"assert Path.home() == Path({str(home)!r}); "
        "assert Path(ai.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()); "
        "from ai.runtime_factory import DefaultProviderFactory; "
        "assert DefaultProviderFactory.create.__name__ == 'reject_provider'; "
        "from ai.runtime_config import validate_config; assert validate_config({}) == {}"
    )
    run([str(python), "-I", "-c", probe], cwd=working)
    # Both of these formerly plausible config locations must be ignored.
    for unrelated in [working / "config", site / "config"]:
        unrelated.mkdir()
        (unrelated / "config.json").write_text('{"unknown": true}')
    config = home / ".config/bookweaver/config.json"
    config.parent.mkdir(parents=True)
    config.write_text('{"sanity_probe": {"enabled": false}}')
    source, output = working / "source.epub", working / "out.epub"
    make_source(source)
    original = source.read_bytes()
    # Scrub inherited Python import overrides while leaving the user's HOME intact.
    child_env = {key: value for key, value in os.environ.items() if not key.startswith("PYTHON")}
    command = [
        str(environment / "bin/bookweaver"),
        str(source),
        "--output",
        str(output),
        "--no-resume",
    ]
    result = run(command, cwd=working, env=child_env)
    assert "[progress:done]" in result
    assert not marker.exists()
    assert source.read_bytes() == original
    with zipfile.ZipFile(source) as before, zipfile.ZipFile(output) as after:
        assert before.namelist() == after.namelist()
        assert all(before.read(name) == after.read(name) for name in before.namelist())
    pristine_output = output.read_bytes()
    for bad in ['{"unknown": true}', '{"sanity_probe": {"heartbeat_chars": 0}}']:
        config.write_text(bad)
        failed = subprocess.run(command, cwd=working, env=child_env, text=True, capture_output=True)
        assert failed.returncode != 0 and "Invalid runtime configuration" in failed.stderr
        assert output.read_bytes() == pristine_output and config.read_text() == bad
        assert not marker.exists()
    config.write_text("{}")
    legacy = home / ".config/translatebook/config.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("{}")
    failed = subprocess.run(command, cwd=working, env=child_env, text=True, capture_output=True)
    assert failed.returncode != 0 and "Legacy" in failed.stderr
    assert output.read_bytes() == pristine_output and legacy.read_text() == "{}"
    assert not marker.exists()
    print(
        json.dumps(
            {"installed_cli": "passed", "artifact_schema": "passed", "provider_constructions": 0}
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--sdist", type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="bookweaver-installed-") as directory:
        verify(args.wheel.resolve(), args.sdist.resolve(), Path(directory))


if __name__ == "__main__":
    main()
