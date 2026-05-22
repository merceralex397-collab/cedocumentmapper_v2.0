# AGENTS.md

Guidance for agents working in `cedocumentmapper_v2.0`.

## Project Status

This is a scaffold for a full replacement of the existing single-file CE Document Mapper. Do not copy large chunks from the v1 `app.py` into this project. Use v1 behavior as reference, then implement behind the v2 contracts.

## Commands

Install runtime and dev dependencies:

```powershell
pip install -r requirements-dev.txt
```

Run tests:

```powershell
pytest
```

Run type checks once configured:

```powershell
mypy src
```

Run linting once configured:

```powershell
ruff check src tests
```

## Architecture Rule

Every document reader must output the canonical `DocumentModel`. Extraction rules must consume that model, not raw file-specific APIs. UI code must not parse documents directly.

## Contract Rule

Before implementing a module, check:

- `docs/contracts/document-model.md`
- `docs/contracts/module-interfaces.md`
- relevant JSON schema files in `docs/contracts/`
- the matching ticket in `docs/tickets/`

If implementation needs a contract change, update the contract and schema in the same change.

## Regression Rule

Any fix for a real document must add or update a fixture under `tests/fixtures/` and an expected output file. Parser changes without fixture coverage should be treated as incomplete.

## Migration Rule

The v1 provider configuration is user data. Migration must be additive and best-effort. Never discard unknown provider fields unless a migration explicitly preserves them in metadata.

