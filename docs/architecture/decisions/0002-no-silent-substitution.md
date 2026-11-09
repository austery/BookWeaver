# ADR-0002: Stop instead of silently changing the model, effort or output

Status: Accepted (2026-11-09). The owner approved it by merging PR 77.

## Context

Translation quality and resume safety depend on knowing what produced each passage. Upstream tools change their models often, and a tool can accept an invalid selection and quietly use another one.

## Decision

A selection that cannot run as asked stops the run with a visible error. The application does not switch model or effort, and it does not truncate or rewrite the source to get past a failure.

## Reason

- Free-form model strings: "Unsafe because invalid strings can silently fall back" (SPEC-020).
- Mapping one tier onto another: "Creates false model identity and misleading checkpoints" (SPEC-020).
- The strict "no silent substitution" rule (SPEC-025).

## Alternatives

Free-form model strings and tier aliases were rejected for the reasons above.

## Consequences

An upstream change can stop a run until the owner updates the model registry.
