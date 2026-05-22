# EPIC-04 Rule Engine

## Objective

Implement field extraction rules against `DocumentModel`.

## Deliverables

- Rule parser from v2 config.
- Rule implementations for current v1 behavior.
- Source span support for extracted values.
- Rule-level confidence and failure reasons.

## Acceptance Criteria

- Current v1 methods are covered: single label, two labels, fixed position, fixed position plus label, label offset, email date, manual input, presence check.
- Rules are unit-tested independently of UI.
- Rule failures return empty values plus issues, not exceptions, unless config is invalid.

