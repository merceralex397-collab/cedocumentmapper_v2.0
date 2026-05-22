# Regression Testing Strategy

## Baseline

The current v1 project has many real sample documents but no committed automated tests. V2 should start by turning those samples into fixtures.

## Fixture Levels

1. Reader fixtures: prove that text, lines, pages, and OCR notes are stable enough.
2. Provider fixtures: prove that provider detection picks the correct preset.
3. Field fixtures: prove expected values for every configured field.
4. Export fixtures: prove final EVA JSON shape and normalization.

## Test Output

Regression tests should print field-level diffs:

- expected provider vs actual provider
- expected field value vs actual field value
- source span if available
- reader notes

## Acceptance Bar

A reader/rule change is acceptable only when:

- all unaffected fixtures remain unchanged, or
- fixture changes are intentionally approved and committed with updated expected files.

