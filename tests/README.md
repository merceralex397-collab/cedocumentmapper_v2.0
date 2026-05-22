# Tests

The v2 test suite should be fixture-first.

Minimum expected groups:

- `tests/contract/`: JSON schema and domain contract tests.
- `tests/regression/`: end-to-end extraction tests over real sample documents.
- `tests/fixtures/`: source documents, expected provider matches, expected field values.

No parser change is complete until a fixture proves the behavior.

