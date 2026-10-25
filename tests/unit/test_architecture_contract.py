"""Check that configured dependency rules reject a real forbidden import."""

from pathlib import Path
import shutil
import subprocess


def test_checkpoint_cannot_import_application(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    shutil.copytree(root / "ai", tmp_path / "ai", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy2(root / "tach.toml", tmp_path / "tach.toml")
    executable = shutil.which("tach")
    assert executable is not None
    clean = subprocess.run([executable, "check"], cwd=tmp_path, capture_output=True, text=True)
    assert clean.returncode == 0, clean.stdout + clean.stderr
    checkpoint = tmp_path / "ai/checkpoint_store.py"
    with checkpoint.open("a") as stream:
        stream.write("\nfrom ai.orchestration import TranslationOrchestrator\n")
    broken = subprocess.run([executable, "check"], cwd=tmp_path, capture_output=True, text=True)
    assert broken.returncode != 0
    assert "ai.orchestration" in broken.stdout + broken.stderr
    assert "ai/checkpoint_store.py" in broken.stdout + broken.stderr
