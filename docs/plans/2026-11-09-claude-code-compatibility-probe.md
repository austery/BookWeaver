# Claude Code compatibility probe (2026-11-09)

**Result:** `claude-sonnet-5-5-low` passes on Claude Code 2.1.311 through the owner's claude.ai login, for both framing protocols. This proves the path runs. It says nothing about book quality. The owner reports no API usage, so the subscription paid by exclusion; the calls were too small to see in the subscription usage.

The owner ran the command in a normal terminal. It used synthetic passages and one tiny synthetic EPUB (two sentences and an eight-entry index), with no book text. `claude-opus-5-5-low` was not called.

## Live results

Command: `uv run bookweaver tiny-indexed.epub --output out.epub --preset claude-sonnet-5-5-low`, with term extraction on in the owner's configuration.

| Step | Protocol | Result |
|---|---|---|
| Compatibility probe for term extraction | `delimiter` | Pass, recorded 22:38:27 UTC |
| Term extraction | `delimiter` | Ran; returned 0 terms from the tiny index |
| Compatibility probe for translation | `segment_tags` | Pass, recorded 22:38:32 UTC |
| Translation, one batch of two segments | `segment_tags` | Both segments translated into Chinese |

- The checkpoint records provider `cli`, backend `claude-code`, model `claude-sonnet-5-5-low`, version `2.1.311 (Claude Code)` for both segments.
- The output EPUB holds each source sentence followed by its Chinese translation.
- Both passes are in `runtime-certifications.json` under runtime `claude-code`.
- No file with the probe passages appeared under `~/.claude/projects` after the run.
- BookWeaver does not count subscription CLI requests. By design this run made four model calls: two probes, one extraction and one translation batch.

An earlier attempt with a book that had no index stopped before any model call, because automatic extraction requires an index. That is the documented behavior of `auto` mode, not a runtime fault.

## Not proven

- A direct measurement that the subscription pool paid. The owner reported on 2026-11-09 that the account shows no API usage, and that four small calls do not move the usage display of a 100-dollar subscription. The same limit applies to the Codex and Antigravity probes. The rest is indirect: discovery requires `authMethod: claude.ai`, and the child environment holds no API key. A full book run would give a visible change.
- The request content under the claude.ai login. The offline capture (`2026-11-09-claude-code-request-capture.md`) used a fake API key.
- Extraction quality: the tiny index yielded 0 terms, as it did for Codex.
- Translation quality on any book, or any comparison between models.
- `claude-opus-5-5-low`.
- A real quota failure, a real expired login, or a real cut reply; those paths were seen only against the fake endpoint.
