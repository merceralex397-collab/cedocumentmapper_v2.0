# Document Model Contract

The document model is the internal representation all readers produce.

## Required Properties

- `source_path`: original file path.
- `source_type`: one of `pdf`, `docx`, `doc`, `eml`, `msg`, `txt`.
- `plain_text`: full readable text for simple search.
- `pages`: ordered pages containing ordered lines.
- `reader_notes`: non-fatal reader diagnostics.
- `metadata`: reader-specific facts such as OCR usage, page count, or attachment names.

Readers should preserve both extraction-friendly lines and any raw line stream that is useful for legacy-compatible positional behavior. When blank-preserving text is available, place it in `metadata.raw_lines` as an ordered array of strings and `metadata.raw_text` as the original normalized line text.

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

Line-position rules must use `metadata.raw_lines` when present, because some provider presets depend on blank-preserving source positions.

