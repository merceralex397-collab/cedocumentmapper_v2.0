# EPIC-02 Reader Layer

## Objective

Implement readers for PDF, DOCX, DOC, MSG, and EML into `DocumentModel`.

## Deliverables

- Reader registry by extension.
- PDF reader using PyMuPDF blocks and pypdf fallback.
- OCR fallback with explicit trigger diagnostics.
- DOCX reader including tables, headers, footers, and text boxes.
- DOC reader using Word COM, LibreOffice fallback, and antiword last resort.
- MSG and EML readers with header/body/attachment-name extraction.

## Acceptance Criteria

- Each reader has isolated tests.
- Reader output includes page/line structure where available.
- Long-running OCR is capped and surfaced in notes.
- Antiword fallback warns that headers/footers may be incomplete.

