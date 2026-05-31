# CLI Parity Plan

## Diagnosis

The current CLI is not at parity with the UI. It is not close to parity.

Current command surface:

```powershell
python app.py
python app.py --dev
python app.py --debug
```

Observed implementation:

- `app.py` only adds `src` to `sys.path`, checks for `--dev` or `--debug`, and calls `start_webview(debug=...)`.
- `pyproject.toml` has no `console_scripts`.
- There is no `argparse`, `click`, `typer`, or equivalent command parser.
- There is no `src/cedocumentmapper_v2/cli.py`.
- All non-GUI actions are exposed only as `WebviewBridge` methods for PyWebView.

Conclusion: the current CLI is a GUI launcher with two debug flags. It cannot import, parse, extract, review, export, extract images, run rules, or manage provider presets headlessly.

## UI Capability Inventory

The CLI must cover every current UI capability:

| UI capability | Current UI path | CLI parity today |
| --- | --- | --- |
| Launch app | `app.py` / `start_webview()` | Partial launcher only |
| Load providers | `WebviewBridge.load_providers()` | No |
| Save providers | `WebviewBridge.save_providers()` | No |
| Add provider preset | React state then `save_providers()` | No |
| Reset/delete provider preset | React state then `save_providers()` | No |
| Edit provider metadata | React provider tab | No |
| Edit field rules | React rules tab | No |
| Live rule sandbox | `WebviewBridge.re_run_rule()` | No |
| Import file by path | `WebviewBridge.import_file()` | No |
| Import file bytes | `WebviewBridge.import_file_data()` | No |
| Detect provider | reader + `ProviderDetector` | No direct CLI |
| Extract fields | `RuleEngine.extract_record()` | No direct CLI |
| Re-extract with chosen provider | `extract_document_with_provider()` | No |
| Engineer report overlay | UI imports second file with `is_engineer_report=True` and merges nonblank fields | No |
| Export EVA JSON | `WebviewBridge.export_json()` | No |
| Export RJS DOCX | `WebviewBridge.export_docx()` | No |
| Extract images | `WebviewBridge.extract_images()` | No |
| PDF preview/base64 | UI-only concern | Not needed in CLI |

## Target CLI Contract

Add an installed command named:

```powershell
cedocumentmapper
```

Also support module execution:

```powershell
python -m cedocumentmapper_v2.cli
```

Use standard-library `argparse` to avoid adding runtime dependencies.

Add this entry point to `pyproject.toml`:

```toml
[project.scripts]
cedocumentmapper = "cedocumentmapper_v2.cli:main"
```

Keep `app.py` as a compatibility launcher, but make it delegate to the same CLI entry point where practical.

## Shared Service Layer

Do not duplicate PyWebView bridge logic in the CLI. Create a shared application service used by both the CLI and `WebviewBridge`.

Recommended module:

```text
src/cedocumentmapper_v2/application/service.py
```

Core service responsibilities:

- Seed, load, migrate, validate, and save providers using the same `APP_DATA_DIR` behavior as the UI.
- Read documents through `get_reader_for_path()`.
- Detect providers through `ProviderDetector`.
- Extract records through `RuleEngine`.
- Re-extract an existing `DocumentModel` with an explicit provider.
- Overlay engineer-report fields onto an instruction record by copying nonblank engineer values over base values for non-provider fields.
- Export EVA JSON and RJS DOCX.
- Extract images from explicit source paths or bytes.
- Return structured results suitable for both UI conversion and CLI JSON output.

The PyWebView bridge should become a thin adapter over this service. The CLI should also use this service directly.

## Command Design

### `cedocumentmapper gui`

Launch the existing PyWebView UI.

```powershell
cedocumentmapper gui
cedocumentmapper gui --dev
cedocumentmapper gui --debug
```

Behavior:

- Equivalent to current `python app.py`.
- `--dev` and `--debug` map to `start_webview(debug=True)`.

### `cedocumentmapper providers list`

Print configured providers.

```powershell
cedocumentmapper providers list
cedocumentmapper providers list --json
```

Default text columns:

- `id`
- `name`
- `work_provider`
- `enabled`
- `priority`
- required detect phrases count

JSON mode prints the same provider objects used by the UI.

### `cedocumentmapper providers show`

Show one provider.

```powershell
cedocumentmapper providers show --id rjs
cedocumentmapper providers show --name "RJS"
cedocumentmapper providers show --id rjs --json
```

Provider lookup precedence:

1. `--id`
2. `--name`

If no provider matches, exit `2`.

### `cedocumentmapper providers export`

Write the full provider catalog to a file or stdout.

```powershell
cedocumentmapper providers export --out providers.v2.json
cedocumentmapper providers export --stdout
```

The exported catalog must be v2 schema shape.

### `cedocumentmapper providers import`

Replace or merge provider catalog from JSON.

```powershell
cedocumentmapper providers import providers.json --replace
cedocumentmapper providers import providers.json --merge
```

Behavior:

- Accept v1 or v2 provider JSON.
- If v1 or missing `schema_version`, migrate first.
- Validate against `provider-config.schema.json`.
- `--replace` overwrites the current provider catalog.
- `--merge` upserts by provider `id`, preserving providers not present in the import.
- Default is `--merge`.

### `cedocumentmapper providers set`

Edit provider metadata without opening the UI.

```powershell
cedocumentmapper providers set --id rjs --name "RJS" --work-provider RJS
cedocumentmapper providers set --id rjs --enabled true --priority 10
cedocumentmapper providers set --id rjs --detect-required "Robert James Solicitors" "RJS"
cedocumentmapper providers set --id rjs --engineer-report false
cedocumentmapper providers set --id rjs --use-current-date-for-inspection-date true
cedocumentmapper providers set --id rjs --force-postcode-for-inspection-address true
```

Behavior:

- Apply only provided fields.
- Save immediately.
- Print the updated provider as JSON unless `--quiet` is set.

### `cedocumentmapper providers delete`

Delete a provider preset.

```powershell
cedocumentmapper providers delete --id rjs
cedocumentmapper providers delete --id rjs --yes
```

Behavior:

- Require `--yes` for non-interactive deletion.
- Exit `2` if provider does not exist.

### `cedocumentmapper rules set`

Set or replace one field rule.

```powershell
cedocumentmapper rules set --provider-id rjs --field vrm --kind label_same_line --labels "Client vehicle registration:"
cedocumentmapper rules set --provider-id rjs --field reference --kind fixed_line --line-number 14
cedocumentmapper rules set --provider-id rjs --field instruction_date --kind email_date --labels "Date:"
cedocumentmapper rules set --provider-id rjs --field vat_status --kind presence --tokens "VAT registered" --value Yes --absent-value No
cedocumentmapper rules set --provider-id rjs --field inspection_date --kind manual --value "{today}"
cedocumentmapper rules set --provider-id rjs --field reference --kind regex --pattern "REF-[0-9]+"
```

Behavior:

- Validate field against `FieldKey`.
- Validate kind against `extraction-rule.schema.json`.
- Save immediately.
- Preserve unknown provider fields.

Important parity note:

- The current v2 schema lacks `absent_value` for `presence`. Add this contract field before claiming full v1/UI parity for VAT and mileage unit behavior.

### `cedocumentmapper rules show`

Show rules for one provider or one field.

```powershell
cedocumentmapper rules show --provider-id rjs
cedocumentmapper rules show --provider-id rjs --field vrm
```

### `cedocumentmapper rules run`

Run one ad hoc rule against a document without saving it.

```powershell
cedocumentmapper rules run document.pdf --field vrm --kind label_same_line --labels "Vehicle Reg:"
cedocumentmapper rules run document.pdf --field reference --rule-json rule.json
```

Behavior:

- Read the document.
- Apply the rule through `RuleEngine.extract_field()`.
- Print a JSON object matching the UI live sandbox response:
  - `value`
  - `raw_value`
  - `rule_id`
  - `confidence`
  - `source_span`
  - `issues`

### `cedocumentmapper read`

Read a document into the canonical model.

```powershell
cedocumentmapper read instruction.pdf
cedocumentmapper read instruction.pdf --json
cedocumentmapper read instruction.pdf --plain-text
```

Behavior:

- `--json` prints the serialized `DocumentModel`.
- `--plain-text` prints only `plain_text`.
- Default prints a short text summary:
  - source path
  - source type
  - page count
  - line count
  - reader notes

### `cedocumentmapper detect`

Detect provider only.

```powershell
cedocumentmapper detect instruction.pdf
cedocumentmapper detect instruction.pdf --json
```

JSON output must match `ProviderMatch` shape.

### `cedocumentmapper extract`

Read, detect, and extract fields.

```powershell
cedocumentmapper extract instruction.pdf
cedocumentmapper extract instruction.pdf --json
cedocumentmapper extract instruction.pdf --provider-id rjs
cedocumentmapper extract instruction.pdf --provider-name "RJS"
```

Behavior:

- If provider is not specified, detect it.
- If provider is specified, bypass detection for extraction.
- Print:
  - document summary
  - provider match
  - fields
  - record issues
  - reader notes
- `--json` prints the structured result.

### `cedocumentmapper process`

One-shot workflow matching the UI's normal document workflow.

```powershell
cedocumentmapper process instruction.pdf --export-json
cedocumentmapper process instruction.pdf --export-docx
cedocumentmapper process instruction.pdf --extract-images
cedocumentmapper process instruction.pdf --out-dir C:\Exports
cedocumentmapper process instruction.pdf --engineer-report report.pdf --export-json
```

Behavior:

- Read and extract the instruction.
- If `--engineer-report` is provided:
  - read/extract the engineer report
  - overlay nonblank engineer values over the instruction for all fields except `work_provider`
  - include overlay metadata in JSON output
- Export requested artifacts.
- Default output directory is the same Desktop directory used by the UI.
- `--out-dir` overrides output location.
- Print paths of created files.

### `cedocumentmapper export json`

Export EVA JSON from either a document or an extracted record JSON.

```powershell
cedocumentmapper export json instruction.pdf
cedocumentmapper export json --record extracted-record.json
cedocumentmapper export json instruction.pdf --provider-id rjs --out C:\Exports\result.json
```

Behavior:

- If input is a document, extract first.
- If `--record` is supplied, export directly from record JSON.
- Refuse blank Work Provider, matching `EVAJsonExporter`.

### `cedocumentmapper export docx`

Export RJS DOCX from either a document or an extracted record JSON.

```powershell
cedocumentmapper export docx instruction.pdf
cedocumentmapper export docx --record extracted-record.json
cedocumentmapper export docx instruction.pdf --out C:\Exports\rjs-letter.docx
```

Behavior:

- Match current UI behavior: output `.docx`, not legacy `.doc`.
- Name output using the same `work_provider` + `vrm` base naming convention.

### `cedocumentmapper images extract`

Extract embedded images.

```powershell
cedocumentmapper images extract instruction.pdf
cedocumentmapper images extract instruction.docx --out-dir C:\Exports
cedocumentmapper images extract instruction.pdf --work-provider RJS --vrm AB12CDE
```

Behavior:

- Support PDF, DOCX, and DOC, matching the UI.
- Default naming uses extracted `work_provider` and `vrm` when available.
- Explicit `--work-provider` and `--vrm` override naming only.

### `cedocumentmapper version`

Print package version and key dependency availability.

```powershell
cedocumentmapper version
cedocumentmapper version --json
```

Include:

- package version
- Python version
- PyMuPDF availability
- pypdf availability
- python-docx availability
- extract-msg availability
- pytesseract availability and configured binary path
- Word COM availability on Windows
- LibreOffice availability

## Output JSON Shapes

Keep JSON output stable and close to current UI bridge objects.

`extract --json` output:

```json
{
  "document": {
    "source_path": "input.pdf",
    "source_type": "pdf",
    "page_count": 1,
    "line_count": 123,
    "reader_notes": []
  },
  "provider": {
    "provider_id": "rjs",
    "provider_name": "RJS",
    "confidence": 1.0,
    "matched_terms": [],
    "missing_terms": [],
    "rejected_terms": []
  },
  "fields": {
    "vrm": {
      "value": "AB12CDE",
      "raw_value": "AB12 CDE",
      "rule_id": "rjs_vrm",
      "confidence": 1.0,
      "source_span": {
        "page_index": 0,
        "line_index": 12,
        "bbox": null
      },
      "issues": []
    }
  },
  "issues": []
}
```

`process --json` should include an `outputs` object:

```json
{
  "outputs": {
    "json_path": "C:\\Users\\...\\Desktop\\RJS_AB12CDE.json",
    "docx_path": null,
    "image_paths": []
  }
}
```

## Exit Codes

Use predictable nonzero codes:

- `0`: success
- `1`: unexpected runtime failure
- `2`: invalid user input, missing file, missing provider, unsupported command option
- `3`: document read failure
- `4`: provider detection failure when detection is required
- `5`: extraction completed but required fields are missing
- `6`: export failure
- `7`: provider config validation failure

If extraction has warnings but required fields are present, exit `0` and print warnings in JSON/text output.

## Implementation Steps

1. Add `src/cedocumentmapper_v2/application/service.py`.
   - Move provider seeding/loading/migration/saving from `WebviewBridge` into this service.
   - Move import/extract/export/image orchestration into the service.
   - Keep the domain readers, detector, rules, normalizers, and exporters unchanged initially.

2. Update `WebviewBridge`.
   - Replace direct business orchestration with calls into the shared service.
   - Preserve current UI return shapes exactly.
   - Keep `pdf_base64` only for UI import responses.

3. Add `src/cedocumentmapper_v2/cli.py`.
   - Implement the command tree with `argparse`.
   - Route all work through the shared service.
   - Implement text and JSON output modes.
   - Keep stdout for requested outputs and stderr for diagnostics.

4. Add package entry points.
   - Add `[project.scripts] cedocumentmapper = "cedocumentmapper_v2.cli:main"` to `pyproject.toml`.
   - Add `src/cedocumentmapper_v2/__main__.py` so `python -m cedocumentmapper_v2` works.
   - Keep `app.py` working as a GUI launcher.

5. Add presence negative-value support before claiming full parity.
   - Extend `extraction-rule.schema.json` with `absent_value`.
   - Update `RuleEngine._extract_presence()` to return `absent_value` when tokens are absent.
   - Update migration so VAT maps to `value="Yes", absent_value="No"` and mileage unit maps to `value="Miles", absent_value="Km"` where appropriate.
   - Update UI rule editor to expose "Value if Absent" for presence rules.
   - CLI `rules set` must support `--absent-value`.

6. Add fixed-line range support before claiming full parity.
   - Extend the v2 rule contract with optional `line_end`.
   - Update migration to preserve v1 configs like `3-5`.
   - Update rule engine to join selected nonblank lines or preserve v1 semantics as specified.
   - Add CLI support via `--line-number` and `--line-end`.

7. Restore v1-compatible label behavior before claiming extraction parity.
   - Either add a new rule kind `label_same_or_next_line`, or add a boolean option such as `fallback_next_line` to `label_same_line`.
   - Migration from v1 `single_label` should use this behavior.
   - UI should expose this as a rule type or option.
   - CLI should support it.

8. Add tests.
   - CLI parser smoke tests for every command group.
   - Golden JSON tests for `read`, `detect`, `extract`, `rules run`, and `process`.
   - Provider import/export round-trip tests for v1 and v2 configs.
   - Export tests using temporary output directories.
   - Image extraction tests where fixtures are available.
   - Engineer-report overlay tests.
   - CLI/UI service parity tests comparing `WebviewBridge` output with service/CLI output.

9. Add docs.
   - Update `README.md` with real CLI usage.
   - Add `docs/operations/cli.md` with command examples and exit codes.
   - Note that `gui` is the graphical app launcher and all other commands are headless.

## Acceptance Criteria

The CLI can be considered at full UI parity when all of the following are true:

- `cedocumentmapper gui` launches the same UI as `python app.py`.
- Every PyWebView bridge operation has a CLI equivalent, except UI-only PDF preview/base64.
- Provider configs can be listed, shown, imported, exported, edited, and deleted from CLI.
- Field rules can be shown, set, and sandbox-run from CLI.
- A document can be read, provider-detected, extracted, and exported without opening the UI.
- A provider can be explicitly selected for extraction, matching the UI provider dropdown re-extraction behavior.
- Engineer report overlay can be performed from CLI.
- JSON export, RJS DOCX export, and image extraction work from CLI with configurable output directories.
- CLI output paths use the same naming rules as the UI.
- CLI and UI share one application service rather than duplicating business logic.
- Tests cover all command groups and key workflows.

## Current Verdict

Current CLI parity status: failed.

The current CLI is a launcher only. It has roughly 5 percent of the UI capability surface, because it can start the app but cannot perform the application's document-mapping workflows headlessly.

