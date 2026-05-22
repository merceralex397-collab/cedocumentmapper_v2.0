# Module Boundaries

## Readers

Input: file path.

Output: `DocumentModel`.

Readers may use PyMuPDF, pypdf, Word COM, LibreOffice, python-docx, extract-msg, or OCR. They must not know provider names or EVA field names.

## Detection

Input: `DocumentModel`, provider config.

Output: `ProviderMatch`.

Detection may inspect text and metadata. It must emit matched, missing, and rejected phrases for diagnostics.

## Rules

Input: `DocumentModel`, rule config.

Output: `FieldExtraction`.

Rules must not write files or call UI APIs. They should return source spans whenever possible.

## Normalization

Input: raw extracted field value.

Output: normalized field value plus issues.

Normalization is field-specific and deterministic.

## Exporters

Input: reviewed extracted record.

Output: serialized target format.

The EVA JSON exporter must preserve display-field order even though JSON objects are logically unordered.

## UI

Input: application services.

Output: user-reviewed values and commands.

The UI should not contain parsing logic.

