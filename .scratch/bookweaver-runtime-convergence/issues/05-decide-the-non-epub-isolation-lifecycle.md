# Decide the Non-EPUB Isolation Lifecycle

Type: grilling
Status: open
Triage: ready-for-human
Blocked by: 01

## Question

For Markdown, PDF, DOCX, and `translatebook.sh`, which artifacts should be retained in place, quarantined behind an isolated package, archived through Git history, reduced to a migration stub, or removed?

The decision must preserve realistic future reuse of Markdown and PDF without making them Supported Product Paths or allowing them to shape the new EPUB application interface. DOCX usage is rare and receives no preservation presumption beyond Git history.

## Comments
