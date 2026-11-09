---
specId: SPEC-022
title: Application Module Depth
status: Ready for Implementation
implementationStatus: Verified locally; pending PR merge
priority: P2 - Enhancement
creationDate: 2026-09-12
lastUpdateDate: 2026-09-12
owner: User (AI-Assisted)
relatedSpecs:
  - SPEC-021
tags: [application, testability, runtime-audit, prompt, epub]
---

# SPEC-022: Application Module Depth

## 1. Goal

Concentrate runtime, prompt, and EPUB knowledge behind honest typed Interfaces so current application behavior can be changed and verified locally.

## 2. Authority and scope

The owner authorized the assessment's four improvements and autonomous progression through specification, tickets, implementation, and independent code review on 2026-09-12. Base: `ee2e8d7934661b7d9cff78f4456cf3411cda3036` on `main`. Publication to a task-owned branch and PR is authorized; merge is not.

SPEC-021 remains authoritative for model selection, paid authorization, retries, checkpoint compatibility, segmentation, and book acceptance. This increment does not retire historical scripts, change translation quality policy, authorize external book transmission, or claim whole-book acceptance. Historical code remains until the separate retirement gates pass.

## 3. Decisions and rationale

1. Keep the three-argument format entrypoints and the provider-agnostic engine. Inventory every test class in the historical CLI test module. Move reusable application behavior coverage to the current application Interface; explicitly identify superseded fallback/config/v1 behavior and retained private helper tests. Keep historical tests as retirement evidence, clearly named as such.
2. Make invocation audit operations part of the declared factory Interface and expose optional runtime version through the provider Interface. Remove concrete runtime type checks from current orchestration. Missing usage remains unavailable, not invented zero usage. Audit finalization covers glossary and translation failures and full resume; lazy construction and paid consent remain unchanged. Audit failure must be visible and must not replace an already active translation failure.
3. Resolve prompt templates locally before any glossary/provider work. Freeze template contents for the invocation, render using the existing language/glossary/custom-instruction semantics, and return effective text with its hash. Move existing prompt helpers into this Module and re-export them for historical callers. Keep the effective default prompt byte-identical. Centralize glossary cache identity beside this preparation logic without changing cache keys or reuse rules. Preserve checkpoint hard preflight before extraction, and complete prompt compatibility validation before translation.
4. Replace EPUB Adapter's four injected implementation functions and signature introspection with direct typed package operations. Use real synthetic EPUBs through the source Interface for spine order, media types, IDs, reordered translations, bibliography/table preservation, unchanged resources, and empty publications. Retain focused package tests and external filesystem fault tests. Extend Tach to current top-level Modules with explicit permitted dependencies; do not disable cycle checks or declare everything a utility.

| Alternative | Decision and reason |
| --- | --- |
| Add a generic plugin/session framework | Rejected: no current caller needs it; adds Interface cost. |
| Continue concrete-type checks for audit | Rejected: injected Adapters cannot provide equivalent evidence. |
| Change the checkpoint schema or database | Rejected: no measured durability/performance need. |
| Delete all historical code now | Deferred: SPEC-021 reader/book/retirement gates remain open. |
| Load templates again after glossary extraction | Rejected: mutable files can change the effective request mid-invocation. |

## 4. Ordered tickets

- T1: Inventory and migrate current application behavior tests; identify historical-only coverage.
- T2: Declare runtime audit Interface and cover failure/finalization behavior.
- T3: Introduce prompt preparation with early validation and stable effective identity.
- T4: Simplify EPUB internal Interface and enforce actual module dependencies.

T1 establishes baseline evidence before T2-T4. Each implementation slice has its own commit. Review compares the immutable final head against the base and this SPEC; required fixes precede publication.

## 5. Acceptance

- [x] Every historical CLI test class is classified in the ticket ledger; current application tests cover input rejection, profile/batch selection, glossary selection/injection, sanity-before-persistence, and resume behavior.
- [x] Orchestration contains no concrete Antigravity/DefaultProviderFactory type checks; an injected factory can contribute usage and audit evidence through its declared Interface.
- [x] Full resume constructs zero providers and leaves checkpoint bytes unchanged; mixed-provider provenance and single-attempt paid behavior remain covered offline.
- [x] Glossary/translation failures finalize audit; unavailable runtime/version/usage stays explicit; an audit failure cannot mask an original execution failure.
- [x] Invalid/missing/incompatible templates fail before provider creation, including extraction requests; existing effective prompts and cache keys retain compatibility.
- [x] Prompt hash matches the exact text passed to the provider; changed prompt triggers existing soft-mismatch behavior.
- [x] EPUB source has no `Any`, reflection, or injectable extraction/patching functions; real-package behavior tests replace those implementation mocks.
- [x] Tach explicitly covers application, runtime factory, runtime config, checkpoint, provider, prompt preparation, and EPUB package Modules. A forbidden dependency probe fails.
- [x] Ruff lint/format, full pytest, Tach, and package build pass. No live runtime calls are part of acceptance.
- [x] Independent Standards and Spec reviews resolve all actionable findings; PR records any remaining limitations.

## 6. Status history

| Date | Status | Evidence |
| --- | --- | --- |
| 2026-09-12 | Ready for Implementation | Owner authorized ordered autonomous delivery; original acceptance gaps retained. |


## 7. Implementation evidence

Implementation and independent review are complete; the status above does not claim production acceptance or merge. Delivery is split into runtime/prompt and EPUB/dependency PRs. See the [delivery ledger](../../plans/2026-09-12-module-depth-tickets.md) and versioned review reports for exact source commits, test counts, corrections, and retained limitations.
