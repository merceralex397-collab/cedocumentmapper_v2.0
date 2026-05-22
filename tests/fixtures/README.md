# Fixture Corpus

Each real-world sample should use this shape:

```text
fixtures/
  instructions/
    SBL 01.pdf
  expected/
    SBL 01.expected.json
```

Expected files must validate against `docs/contracts/expected-fixture.schema.json`.

Do not commit private data without approval. If redaction is required, preserve the layout and labels that the parser depends on.

