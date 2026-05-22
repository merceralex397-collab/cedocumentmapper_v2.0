# EPIC-05 Normalization and Validation

## Objective

Normalize field values and validate records before export.

## Deliverables

- VRM normalization.
- Date normalization to `DD/MM/YYYY`.
- Six-line inspection address normalization.
- Mileage numeric extraction.
- VAT and mileage-unit normalization.
- Required-field and suspicious-value validators.

## Acceptance Criteria

- Empty inspection address exports as six blank lines.
- Date fields export as `DD/MM/YYYY` or raise validation issues.
- Mileage contains digits only.
- UI receives validation issues for user review.

