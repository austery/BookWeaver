# ADR-0008: Isolated runtime configuration for subscription CLIs

Status: Accepted (2026-11-11). Approved by the owner in conversation.

## Context

Subscription CLIs (such as Codex and Claude Code) typically read user-level configuration files (`CLAUDE.md`, global instructions, project memories, MCP skills, and interactive agent hooks). When invoking these CLIs programmatically to translate books or judge terminology, user-level developer instructions can leak into prompts, alter output formats, or consume unnecessary tokens.

## Decision

Subscription CLI providers execute inside isolated runtime environments:
- Codex runs with a dedicated private home (`CODEX_HOME=$XDG_STATE_HOME/bookweaver/codex-home`), completely isolated from the user's coding agent configuration.
- Claude Code runs with flags and isolated working directories that exclude local `CLAUDE.md`, project memories, and skills from translation requests.

## Reason

- "The owner's personal coding rules, prompt preferences, and skills must never leak into book translation or term evaluation." (SPEC-025 §3.9)
- "Isolating the runtime environment guarantees deterministic prompt hashes, reproducible checkpoints, and clean schema boundaries." (SPEC-025 §3.10)

## Alternatives

- Running CLIs with the user's default environment and attempting to override instructions inside the prompt: rejected because system prompts and personal memories can still interfere unpredictably with delimiter parsing and structured output.
- Re-implementing CLI protocols natively via raw reverse-engineered endpoints: rejected as brittle and violating subscription tool boundaries.

## Consequences

A one-time login setup is required for isolated environments (e.g. `CODEX_HOME=<path> codex login`). Updates to CLI tools require re-verifying that prompt isolation remains intact.
