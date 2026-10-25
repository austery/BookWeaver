# Audit the Canonical EPUB Runtime

Type: task
Status: open
Triage: ready-for-agent
Blocked by:

## Question

What behavior, modules, tests, and compatibility promises are actually exercised by the canonical `uv run bookweaver <input.epub>` path today, and which top-level modules are live, compatibility-only, test-only, or dead?

The answer must establish a behavior baseline for translation, glossary extraction, sanity checking, checkpoint persistence, output packaging, provider construction, and CLI error handling. It must identify contradictions between README, contributor guidance, completed SPECs, and live code without changing implementation.

## Comments
