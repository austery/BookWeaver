# ADR-0001: Subscription tools first; paid calls only by consent for one run

Status: Accepted (2026-11-09). The owner approved it by merging PR 77.

## Context

BookWeaver exists because per-request translation is costly for whole books, while subscription quota is already paid for. A failed subscription call could be retried on a paid API, which looks convenient.

## Decision

A run uses a subscription tool by default. A paid call needs a person's explicit consent for that one run. A subscription failure never starts a paid call.

## Reason

- "Technical availability is not authorization to spend money. A CLI failure must never trigger Gemini API usage automatically." (SPEC-020)
- "Config, environment, and checkpoints cannot authorize spending." (SPEC-021)

## Alternatives

- Automatic fallback to the paid API. Rejected: "Can create an unbounded cost spike without informed consent" (SPEC-020).
- Consent stored in configuration, the environment or a checkpoint. Rejected for the reason above.

## Consequences

A run can stop on a quota limit when a paid call could have continued it. The person decides what happens next.
