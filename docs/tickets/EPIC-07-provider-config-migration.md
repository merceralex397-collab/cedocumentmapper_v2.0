# EPIC-07 Provider Config Migration

## Objective

Migrate v1 `providers.json` into the v2 provider schema.

## Deliverables

- v1 schema reader.
- v1-to-v2 rule mapping.
- Preservation of unknown provider metadata.
- Migration report listing lossy or ambiguous conversions.

## Acceptance Criteria

- Current v1 `providers.json` migrates without crashing.
- Every migrated provider has an id, name, work provider, detection config, and field rules.
- Migrated config validates against `provider-config.schema.json`.
- Migration is covered by tests.

