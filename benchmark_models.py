#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from ai.gemini_provider import GeminiProvider


DEFAULT_MODELS: tuple[str, str] = ("gemini-2.5-flash", "gemini-2.5-pro")


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    file_name: str
    model: str
    output_chars: int


def sample_chunk_files(temp_dir: Path, sample_count: int) -> list[Path]:
    all_chunks = sorted(temp_dir.glob("page*.md"))
    if not all_chunks:
        raise ValueError(f"No page*.md files found in {temp_dir}")

    if sample_count <= 0:
        raise ValueError("sample_count must be > 0")

    if len(all_chunks) <= sample_count:
        return all_chunks

    indexes: list[int] = [0]
    if sample_count >= 2:
        indexes.append(len(all_chunks) // 2)
    if sample_count >= 3:
        indexes.append(len(all_chunks) - 1)

    while len(indexes) < sample_count:
        candidate = (len(all_chunks) * len(indexes)) // sample_count
        if candidate not in indexes:
            indexes.append(candidate)
        else:
            candidate += 1
            if candidate < len(all_chunks) and candidate not in indexes:
                indexes.append(candidate)
            else:
                break

    unique_sorted_indexes = sorted(set(indexes))[:sample_count]
    return [all_chunks[index] for index in unique_sorted_indexes]


def run_benchmark(
    temp_dir: Path,
    sample_count: int,
    output_lang: str,
    prompt: str,
    models: tuple[str, ...] = DEFAULT_MODELS,
) -> dict[str, object]:
    samples = sample_chunk_files(temp_dir=temp_dir, sample_count=sample_count)
    results: list[BenchmarkResult] = []

    for sample in samples:
        text = sample.read_text(encoding="utf-8")
        for model in models:
            provider = GeminiProvider(model=model)
            translated = provider.translate_chunk(
                text=text,
                chunk_size=len(text),
                system_prompt=f"{prompt}\nTarget language: {output_lang}",
            )
            results.append(
                BenchmarkResult(
                    file_name=sample.name,
                    model=model,
                    output_chars=len(translated),
                )
            )

    return {
        "temp_dir": str(temp_dir),
        "sample_count": sample_count,
        "models": list(models),
        "results": [
            {
                "file_name": item.file_name,
                "model": item.model,
                "output_chars": item.output_chars,
            }
            for item in results
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark Gemini models on sample chunks")
    parser.add_argument("--temp-dir", required=True, help="Directory containing page*.md files")
    parser.add_argument("--sample-count", type=int, default=3, help="Number of sampled chunks")
    parser.add_argument("--output-lang", default="zh", help="Target language")
    parser.add_argument(
        "--prompt",
        default="Translate while preserving Markdown formatting.",
        help="System prompt used for benchmark calls",
    )
    parser.add_argument(
        "--output-json",
        default=str(Path.home() / ".config" / "translatebook" / "model_benchmarks.json"),
        help="Output JSON path",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    temp_dir = Path(args.temp_dir).expanduser().resolve()
    report = run_benchmark(
        temp_dir=temp_dir,
        sample_count=args.sample_count,
        output_lang=args.output_lang,
        prompt=args.prompt,
    )
    output_path = Path(args.output_json).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Benchmark report saved to: {output_path}")


if __name__ == "__main__":
    main()
