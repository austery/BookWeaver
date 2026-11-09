# Codex compatibility probe (2026-11-09)

**Result:** `gpt-6-luna` and `gpt-6.1-sol` at low effort pass on codex-cli 0.167.0, through the private ChatGPT login. This proves the path runs. It says nothing about book quality.

The owner authorized these calls in the session. They used synthetic passages and one tiny synthetic EPUB, with no book text. `gpt-6.1-terra` and `gpt-6-astra` were not called.

## Live results

| Preset | Protocol | Calls | Time | Result |
|---|---|---|---|---|
| `codex-gpt-6-luna-low` | `segment_tags` | 2 | 15.6 s | Pass |
| `codex-gpt-6-luna-low` | `delimiter` | 1 | 12.6 s | Pass |
| `codex-gpt-6.1-sol-low` | `segment_tags` | 2 | 18.0 s | Pass |
| `codex-gpt-6.1-sol-low` | `delimiter` | 1 | 8.0 s | Pass |

- These runs used the fixed Chinese probe prompt, and their certifications went to a temporary file. A real run still probes with its own prompt.
- End to end: `bookweaver <tiny.epub> --preset codex-gpt-6-luna-low --extract-glossary --extraction-model flash` finished in 25 s. The checkpoint records provider `cli`, backend `codex`, model `gpt-6-luna-low`, version `codex-cli 0.167.0`. Term extraction also ran on Luna and returned 0 terms from the tiny index, so this run does not show extraction quality.

## Offline request capture

The real CLI ran against a local fake provider, with a fake key and a temporary `CODEX_HOME`, to show the exact request.

| Setting | Fixed context, characters | Owner `AGENTS.md` sent |
|---|---|---|
| `--ignore-user-config --ignore-rules` only | 36,108 | Yes |
| Adding `project_doc_max_bytes=0` | 36,108 | Yes |
| Adding `agents_md.*` | 36,108 | Yes; Codex reports the key as ignored |
| Production arguments in a home without `AGENTS.md` | about 2,800 | No |

Other observed behavior:

- `OPENAI_BASE_URL` does not redirect `codex exec` under `--ignore-user-config`. An early capture run therefore sent a fake key to `api.openai.com` and received 401. No real credential or quota was involved. The harness then used an explicit local `model_provider`.
- A fake HTTP 429 becomes a `turn.failed` event with "You've hit your usage limit". A fake HTTP 401 retries five times, then fails.
- `codex login status` writes to stderr. Without a login it exits 1 with `Not logged in`.
- `codex debug models` works without a login.
- With `--ephemeral`, the prompt was not found under `CODEX_HOME` or the workspace after a run.

## Not proven

- Translation quality on any book, or any comparison between models.
- That the subscription pool paid for these calls. The evidence is indirect: a ChatGPT login and no API key in the child environment.
- A real quota failure or a real expired login; those two error paths were seen only against the fake server.
- A hang during a real run; only the outer deadline guards it.
- The request shape under a ChatGPT login may differ from the fake provider's; the probe covers the output, not that request.
