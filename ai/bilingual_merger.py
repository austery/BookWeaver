from __future__ import annotations


class BilingualMerger:
    def merge(self, original_chunks: list[str], translated_chunks: list[str]) -> str:
        if len(original_chunks) != len(translated_chunks):
            raise ValueError("original_chunks and translated_chunks must have same length")

        blocks: list[str] = []
        for index, (original, translated) in enumerate(
            zip(original_chunks, translated_chunks), start=1
        ):
            blocks.append(
                "\n".join(
                    [
                        f"## Segment {index}",
                        "",
                        original.strip(),
                        "",
                        "**中文译文**",
                        "",
                        translated.strip(),
                        "",
                        "---",
                        "",
                    ]
                )
            )
        return "".join(blocks).strip() + "\n"
