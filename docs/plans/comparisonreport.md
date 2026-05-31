# CE Document Mapper v1 vs v2 Comparison Report

## Executive Summary

The original `cedocumentmapper` can currently extract specific business data that `cedocumentmapper_v2.0` often cannot, even when v2 can read the same file.

The biggest issue is not file-format support. It is rule semantics. In v1, `single_label` means "same line, or next useful line if the label line has no value." In v2, migration maps that to `label_same_line`, which only handles same-line values. That causes many real fields to go blank in v2.

Across 94 non-DOC corpus files from `docs/Instructions`:

- 94 files read without parser failure.
- 3 image-only files were unmapped in both.
- 91 files were comparable.
- Provider detection matched between v1 and v2 for all comparable files.
- 82 of 91 comparable files had at least one field-level difference.
- Many differences are just v2 date normalization, but many are real v1-wins/v2-blanks.

The v2 test suite passed during this read-only investigation:

```text
36 passed, 1 skipped
```

The skipped test was the legacy `.DOC` reader test because this machine does not currently have a DOC-reading dependency available.

## Specific Data v1 Gets That v2 Misses

From the corpus comparison, these are cases where v1 returned a nonblank value and v2 returned blank:

| Field | v1 nonblank / v2 blank count |
| --- | ---: |
| `vrm` | 33 |
| `incident_date` | 29 |
| `claimant_name` | 24 |
| `reference` | 24 |
| `vehicle_model` | 23 |
| `inspection_address` | 18 |
| `inspection_date` | 12 |
| `instruction_date` | 10 |
| `vat_status` | 10 |

Examples:

- ALISON PDFs: v1 extracts `incident_date` and `inspection_address`; v2 blanks both.
- BLACK PDFs: v1 extracts `vrm`, `reference`, and `inspection_address`; v2 blanks them.
- DFD PDFs: v1 extracts `vrm`, `claimant_name`, `reference`, `incident_date`, `instruction_date`, and `inspection_address`; v2 blanks most or all of those fields.
- FW `.msg` files: v1 extracts VRM and vehicle model; v2 often blanks them and sometimes extracts claimant as literal `Name`.
- QDOS and SBL PDFs: v1 extracts VRM, vehicle model, claimant, reference, and incident date; v2 blanks them.
- AX and SBL VAT: v1 can return `No`; v2 returns blank.

## Root Causes

### 1. `single_label` Regression

v1 `extract_after_label()` supports same-line and next-line extraction. v2 has separate `label_same_line` and `label_next_line`, but migration maps v1 `single_label` only to `label_same_line`.

That breaks many provider presets where labels and values are split across lines.

### 2. Fixed-Position Line Numbering Changed

v1 fixed-position rules run over `text.splitlines()`, including blank-line structure. v2 readers usually omit blank lines from `DocumentLine`, so `fixed_line` points at different content.

Example: AX instruction date becomes `Engineer Instructions` in v2.

### 3. Presence Checks Lost Negative Values

v1 presence fields return configured negative values:

- VAT status: `Yes` or `No`
- Mileage unit: `Miles` or `Km`

v2 `presence` currently supports only "value if present" or blank. This causes real data loss for negative VAT and Km inference.

### 4. Legacy/Fallback Extractors Are Absent in v2

v1 still has built-in fallback methods for:

- reference
- VRM
- claimant name
- vehicle model
- address
- letterhead date
- date near keywords

Current shipped providers do not use these methods directly, but older user configs could. v2 migration does not preserve those semantics.

### 5. PDF Text Structure Differs

v1 uses PyMuPDF block mode and preserves blank separation between blocks. v2 uses dict-line extraction with source spans, which is structurally better, but currently collapses some blank/block separation that v1 extraction rules depended on.

### 6. Provider Config on Disk Is Still v1-Shaped

Both repos' `providers.json` files are v1-style. v2 relies on runtime migration in `src/cedocumentmapper_v2/config/migration.py`.

That migration is functional enough to pass tests, but it is not semantically equivalent to v1.

## Capabilities v1 Has That v2 Does Not Yet Match

- Batch drag/drop and batch export.
- Smart engineer-report pairing and overlay workflows.
- Legacy `.doc` fallback through `antiword`.
- Export to legacy `.doc` via Word, with `.docx` fallback.
- Presence checks with explicit positive and negative values.
- Combined same-line-or-next-line label extraction.
- Fixed-position ranges such as `3-5`.
- Legacy fallback extractors for VRM, reference, claimant name, vehicle model, address, and dates.

## Where v2 Is Ahead

- Cleaner architecture around `DocumentModel`.
- Source spans, confidence, and validation issues.
- Generic `regex` rule support.
- Fuzzy label matching, useful for OCR typos.
- Safer OCR cap, avoiding the old long-freeze case on big scanned PDFs.
- React/PyWebView UI is more extensible than the v1 Tkinter monolith.

## README, CLI, and Repo State

### README

`README.md` is stale. It still says the repo is scaffold-only and that the production app is not implemented, but v2 now has:

- `app.py`
- frontend UI
- PyWebView host
- readers
- rules
- exporters
- tests

### CLI

There is only a launcher, not a formal installed CLI:

```powershell
python app.py
python app.py --dev
python app.py --debug
```

`pyproject.toml` does not define `console_scripts`.

### Unstaged State

The unstaged state is large:

- Modified tracked config/package files.
- Many untracked implementation modules.
- Frontend files.
- Instructions corpus files.
- Fixtures and tests.

## Performance Note

The startup/import performance issue is likely around frontend/PyWebView readiness plus PDF base64 duplication:

- React polls every 100 ms for `window.pywebview.api`.
- Path-based PDF imports base64-encode the full PDF and send it to the frontend.
- The frontend decodes that PDF back into a Blob.
- Large PDFs duplicate memory and can stall the UI.

A better approach would be to serve the local PDF through the PyWebView HTTP server or return a file token/path instead of base64.

## Bottom Line

v2 can read the same broad document formats, but it does not yet reproduce v1's extraction behavior.

The most urgent parity fixes are:

1. Restore v1 `single_label` semantics.
2. Preserve fixed-position line behavior or migrate configs differently.
3. Add negative values to `presence`.
4. Add regression fixtures for providers where v1 currently beats v2.

