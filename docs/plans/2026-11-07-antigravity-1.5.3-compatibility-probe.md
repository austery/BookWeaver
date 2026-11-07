# Antigravity 1.5.3 compatibility probe

## Context

- Date: 2026-11-07. The owner's local `agy` auto-updated from the certified `1.1.27` to `1.5.3`.
- The default CLI path stopped at the version gate: `Antigravity 1.5.3 requires a compatibility probe before updating CERTIFIED_AGY_VERSIONS`. No model call was made.
- SPEC-021 requires a probe before certifying a new CLI version.

## Method

`scripts/probe_antigravity_version.py`, run on the owner's machine. Three synthetic English passages go through the production path: `build_system_prompt(..., immersive=True)`, segment-tag framing, `AntigravityProvider` invocation, and `split_response`. Checks: three ordered, non-empty segments containing Chinese, with no fences or artifact links. No book content was sent.

## Result

| Profile | Model | Elapsed | Result |
|---|---|---:|---|
| flash / low | `gemini-3.8-flash-low` | 9.5 s | PASS |
| pro / low | `gemini-3.1-pro-low` | n/a | FAIL: model absent from `agy models` on 1.5.3 |

Flash output, checked manually:

1. 那把旧钥匙藏在花园大门旁一个破损的花盆下面。
2. 断电时，程序从上次保存的检查点恢复运行，而不是重新开始。
3. 透过小型望远镜，她数出了环绕着那颗明亮行星的四颗卫星。

All three are faithful and in order.

## Decision

- `1.5.3` is added to `CERTIFIED_AGY_VERSIONS`. The default `--model flash` path is verified on it.
- `--model pro` still fails loudly at discovery on 1.5.3. Model discovery stays strict, so there is no silent substitution. The Pro mapping is replaced only after the 1.5.3 model roster is read and the replacement passes this probe.

This is a three-passage protocol probe. It does not certify book-length reliability on 1.5.3.

## Follow-up: SPEC-025 Phase 1 (same day)

Live checks on agy `1.5.3` showed that effort is a separate axis: `--model gemini-3.8-flash-low --effort high` is rejected as a conflict, while `--model gemini-3.8-flash --effort high` resolves to `gemini-3.8-flash-high`. An unknown family (`gemini-3.1-pro`) is rejected loudly, without substitution.

Phase 1 changes:

- The registry holds named rows: model family plus owner-enabled efforts. The provider passes the family and passes effort once.
- `pro` maps to `gemini-4-argon` (status `experiment`).
- An unknown agy version triggers the synthetic three-passage probe automatically; a pass is recorded per `(version, model_id, protocol)` in `~/.local/state/bookweaver/runtime-certifications.json`.
- Run audits record `row_status`.

Live verification on the owner machine, with the seed version list emptied to force the automatic probe:

| Row | Probe + 2-passage batch | Elapsed |
|---|---|---:|
| flash / low (`gemini-3.8-flash-low`, default) | PASS | 16.6 s |
| pro / low (`gemini-4-argon-low`, experiment) | PASS | 36.4 s |

The same forced probe with the `delimiter` protocol (used by glossary extraction) passed for both rows.

End-to-end CLI on the generated 8-segment test EPUB: `--model pro` (glossary extraction and translation on Argon) and the default flash run both completed; audits show `row_status` `experiment` and `default`.

This does not certify book-length quality for Argon; pro stays `experiment` until the evaluation in SPEC-025 §3.7.
