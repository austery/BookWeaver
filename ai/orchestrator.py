from __future__ import annotations

import time
from pathlib import Path
from typing import Callable
from typing import Any

from ai.artifacts import OrchestrationArtifacts
from ai.gemini_provider import GeminiProvider
from ai.orchestration_analysis import build_analysis_markdown
from ai.orchestration_context import load_orchestration_context
from ai.orchestration_prompt import build_orchestration_prompt


def run_orchestrated_translation(
    *,
    temp_dir: Path,
    pages: dict[str, str],
    output_lang: str,
    model: str = "gemini-2.5-flash",
    custom_prompt: str | None = None,
    translate_fn: Callable[[str, str], str] | None = None,
    max_retries: int = 3,
    runtime_config: dict[str, Any] | None = None,
    phase: str = "translate",
) -> dict[str, str]:
    if phase not in {"prompt-only", "translate"}:
        raise ValueError(f"Unsupported orchestrated phase: {phase}")

    artifacts = OrchestrationArtifacts(temp_dir=temp_dir)
    context = load_orchestration_context(
        runtime_config=runtime_config or {},
        output_lang=output_lang,
    )
    analysis = build_analysis_markdown(
        pages=pages,
        context=context,
    )
    prompt = build_orchestration_prompt(
        output_lang=output_lang,
        context=context,
        analysis_markdown=analysis,
        additional_instructions=custom_prompt,
    )
    artifacts.write_text(artifacts.analysis_path(), analysis)
    artifacts.write_text(artifacts.prompt_path(), prompt)

    if phase == "prompt-only":
        artifacts.write_metrics(
            {
                "mode": "orchestrated",
                "phase": phase,
                "pages": len(pages),
                "model": model,
                "prompt_length": len(prompt),
            }
        )
        return {}

    provider = GeminiProvider(model=model)

    def _translate(text: str) -> str:
        last_error: Exception | None = None
        for attempt in range(max_retries):
            try:
                if translate_fn is not None:
                    return str(translate_fn(text, prompt))
                return provider.translate_chunk(
                    text=text,
                    chunk_size=len(text),
                    system_prompt=prompt,
                )
            except Exception as exc:  # explicit retry with terminal raise
                last_error = exc
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                raise
        if last_error is not None:
            raise last_error
        raise RuntimeError("Unexpected translation state")

    translated_pages: dict[str, str] = {}
    failed_pages: list[str] = []
    failed_page_errors: dict[str, str] = {}
    for filename, content in pages.items():
        try:
            translated_pages[filename] = _translate(content)
        except Exception as exc:
            failed_pages.append(filename)
            failed_page_errors[filename] = str(exc)
            continue

    critique = (
        "## Critique\n"
        "- Verify fidelity and terminology consistency.\n"
        "- Check markdown structure preservation.\n"
    )
    artifacts.write_text(artifacts.critique_path(), critique)
    artifacts.write_text(artifacts.revision_path(), "\n".join(translated_pages.values()))
    artifacts.write_text(artifacts.polish_path(), "\n".join(translated_pages.values()))
    artifacts.write_metrics(
        {
            "mode": "orchestrated",
            "phase": phase,
            "pages": len(pages),
            "model": model,
            "prompt_length": len(prompt),
            "failed_pages": failed_pages,
            "failed_page_errors": failed_page_errors,
        }
    )
    return translated_pages
