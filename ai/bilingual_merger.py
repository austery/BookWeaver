from __future__ import annotations


class BilingualMerger:
    """Merges original and translated markdown chunks into bilingual format.

    Output format contract: alternating paragraphs (source ¶, translation ¶,
    source ¶, translation ¶, ...). The HTML renderer in 05_md_to_html.py
    depends on this alternating structure to generate bilingual side-by-side
    or stacked layout.
    """

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
