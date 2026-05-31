# Implementation TODOs

This checklist converts the plan documents in `docs/plans` into implementation work items. It is intentionally scoped to v2 contracts and does not copy v1 implementation code.

## CLI Parity

- [x] Add a shared application service used by both UI and CLI.
- [x] Add installed command entry point `cedocumentmapper`.
- [x] Implement `gui`, `read`, `detect`, `extract`, and `process`.
- [x] Implement provider catalog commands.
- [x] Implement rule show/set/run commands.
- [x] Implement export commands for EVA JSON and RJS DOCX.
- [x] Implement image extraction command.
- [x] Add CLI tests for command groups and JSON output.

## Extraction Superiority

- [x] Restore same-line-or-next-line label behavior through an explicit rule kind.
- [x] Support fixed line ranges.
- [x] Support negative presence values.
- [x] Preserve raw line streams where readers can provide them.
- [x] Add fallback candidates for VRM, reference, claimant name, vehicle model, address, and dates.
- [x] Return evidence spans and confidence for fallback decisions.
- [ ] Add regression fixtures for v1-wins from the comparison report.
- [ ] Add a comparator harness for repeatable v1-v2-new-engine scoring.

## Readers

- [x] Add DOC antiword fallback.
- [x] Improve PDF page diagnostics and preserve blank/block separation metadata.
- [x] Improve DOCX table, header/footer, text box, property, and image metadata.
- [x] Improve email metadata, body alternatives, and attachment metadata.
- [ ] Add OCR skip/force diagnostics and caching plan.

## UI/UX and Performance

- [x] Remove avoidable base64 PDF roundtrips on path-based imports.
- [x] Reduce startup polling churn.
- [x] Surface confidence, evidence, alternatives, and validation status more clearly.
- [x] Keep batch, engineer overlay, JSON export, DOCX export, and image extraction workflows accessible.

## Verification

- [x] Run the Python test suite.
- [x] Run focused CLI smoke tests.
- [x] Build the frontend.
- [x] Confirm no regressions or loss of current functionality.
