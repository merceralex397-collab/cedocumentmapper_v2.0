# v1 to v2 Migration Plan

## Inputs

- v1 `providers.json`
- v1 sample documents under `docs/Instructions`
- v1 final JSON examples

## Provider Config Migration

Map v1 concepts to v2:

- `name` -> `name`
- `field_rules.work_provider.config` -> `work_provider`
- `detect_phrases` -> `detect.required_phrases`
- v1 method codes -> v2 rule `kind`
- `engineer_report` -> `engineer_report`
- `force_postcode_for_inspection_address` -> address normalizer option

Unknown fields should be retained under provider metadata during migration.

## Compatibility Policy

The v2 app does not need to preserve the old single-file architecture. It does need to preserve user provider data and the final EVA JSON contract.

## Migration Milestones

1. Build provider config migrator.
2. Convert current `providers.json` into v2 schema.
3. Run migrated providers against the fixture corpus.
4. Fix rule gaps with explicit ticketed changes.

