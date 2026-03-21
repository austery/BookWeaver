from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class OrchestrationArtifacts:
    temp_dir: Path

    def root(self) -> Path:
        return self.temp_dir / "orchestration"

    def analysis_path(self) -> Path:
        return self.root() / "01-analysis.md"

    def prompt_path(self) -> Path:
        return self.root() / "02-prompt.md"

    def translation_dir(self) -> Path:
        return self.root() / "03-translation"

    def critique_path(self) -> Path:
        return self.root() / "04-critique.md"

    def revision_path(self) -> Path:
        return self.root() / "05-revision.md"

    def polish_path(self) -> Path:
        return self.root() / "06-polish.md"

    def metrics_path(self) -> Path:
        return self.root() / "metrics.json"

    def write_text(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def write_metrics(self, payload: dict[str, Any]) -> None:
        metrics_path = self.metrics_path()
        metrics_path.parent.mkdir(parents=True, exist_ok=True)
        metrics_path.write_text(
            json.dumps(payload, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )
