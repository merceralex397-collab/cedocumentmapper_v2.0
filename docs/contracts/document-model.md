# Document Model Contract

The document model is the internal representation all readers produce.

## Required Properties

- `source_path`: original file path.
- `source_type`: one of `pdf`, `docx`, `doc`, `eml`, `msg`, `txt`.
- `plain_text`: full readable text for simple search.
- `pages`: ordered pages containing ordered lines.
- `reader_notes`: non-fatal reader diagnostics.
- `metadata`: reader-specific facts such as OCR usage, page count, or attachment names.

## Line Properties

Each line should include:

- `text`
- `page_index`
- `line_index`
- optional `bbox` for formats with layout coordinates.
- optional `block_id` for grouping.
- optional `confidence`, especially for OCR.

## Rules

Rules should prefer line and coordinate data over reparsing `plain_text` when that makes extraction safer. `plain_text` exists for provider detection and simple label searches.

