# EPIC-08 Regression Harness

## Objective

Build the fixture-based safety net for parser changes.

## Deliverables

- Fixture loader.
- Expected-value diff report.
- Tests for provider, field, and final JSON output.
- Fixture authoring guide.

## Acceptance Criteria

- A new source document can be added with one expected JSON file.
- Test failures identify exact field diffs.
- The harness can run over the current `docs/Instructions` corpus after import.

