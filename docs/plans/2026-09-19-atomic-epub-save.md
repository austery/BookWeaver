# Atomic EPUB save

Approved by the owner on 2026-09-19. Base: b263ee5.

- Keep the existing EPUB save interface and ZIP entry preservation rules.
- Stage in the destination directory; close the complete ZIP and sync its file before replacing the destination atomically.
- Before replacement, failure preserves an existing destination byte-for-byte and leaves an absent destination absent.
- After replacement, directory sync failure explicitly reports that replacement occurred but durability is unconfirmed. Never roll back the replacement.
- Clean up temporary files; cleanup errors must not mask the primary failure.
- Preserve checkpoint behavior, source contents, and SPEC-021 acceptance limits. No live model calls.

Validation: fault injection through the EPUB source adapter for write, file sync, replacement, and directory sync failure; successful ZIP preservation; full repository checks and build; independent Standards and Spec review.
