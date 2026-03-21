from __future__ import annotations

from pathlib import Path

from ai.artifacts import OrchestrationArtifacts


def run_orchestrated_translation(
    *,
    temp_dir: Path,
    pages: dict[str, str],
    output_lang: str,
) -> dict[str, str]:
    artifacts = OrchestrationArtifacts(temp_dir=temp_dir)
    artifacts.write_text(artifacts.analysis_path(), f"analysis for {len(pages)} pages")
    artifacts.write_text(artifacts.prompt_path(), f"translate to {output_lang}")
    artifacts.write_text(artifacts.critique_path(), "critique")
    artifacts.write_text(artifacts.revision_path(), "revision")
    artifacts.write_text(artifacts.polish_path(), "polish")
    artifacts.write_metrics({"mode": "orchestrated", "pages": len(pages)})
    return {name: f"ORCH:{content}" for name, content in pages.items()}
