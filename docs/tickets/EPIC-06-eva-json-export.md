# EPIC-06 EVA JSON Export

## Objective

Serialize reviewed records into the EVA JSON contract.

## Deliverables

- Ordered display-label JSON exporter.
- JSON schema validation before file write.
- Clipboard and file-output application service.
- Filename generation from Work Provider and VRM.

## Acceptance Criteria

- Export matches `docs/contracts/eva-json.schema.json`.
- JSON export is blocked when Work Provider is blank.
- Output path uses the Shell-resolved visual Desktop on Windows.
- Export does not mutate the reviewed record.

