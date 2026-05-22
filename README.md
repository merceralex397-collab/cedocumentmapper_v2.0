# CE Document Mapper v2.0

Architecture scaffold for a replacement CE Document Mapper.

The current production tool extracts key values from PDF, Word, and email instruction documents, then exports an EVA-compatible JSON file. Version 2.0 keeps the same business aim but rebuilds the project around explicit contracts, testable modules, and a regression corpus.

This repository is intentionally scaffold-only at first. Implementation tickets live in `docs/tickets/`.

## Primary Goal

Convert external instruction documents into reviewed, validated EVA JSON with fewer silent extraction errors.

The target output remains the fixed field set:

1. Work Provider
2. VRM
3. Vehicle Model
4. Claimant Name
5. Reference
6. Incident Date
7. Instruction Date
8. Inspection Date
9. Inspection Address
10. Accident Circumstances
11. VAT Status
12. Mileage
13. Mileage Unit

## Design Principles

- Parse documents into a canonical document model before applying rules.
- Keep provider rules explainable and editable by non-developers.
- Treat extraction confidence and validation as first-class output.
- Preserve a human review step before export.
- Build regression tests from real sample instructions before broad refactors.

## Repository Layout

```text
src/cedocumentmapper_v2/
  domain/          Shared field, document, result, and issue models
  readers/         PDF/DOCX/DOC/MSG/EML readers into the document model
  detection/       Provider detection and confidence scoring
  rules/           Rule engine and rule implementations
  normalization/   VRM, date, address, mileage, VAT/unit normalizers
  exporters/       EVA JSON and future API exporters
  config/          Provider config load/save/migration
  ui/              Review and provider setup interface

docs/
  architecture/    System design and module boundaries
  contracts/       JSON schemas and interface contracts
  product/         Requirements and workflow notes
  testing/         Regression strategy and fixture format
  migration/       v1 to v2 migration plan
  operations/      Packaging and release guidance
  tickets/         Implementation tickets by module
```

## Development Commands

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
pytest
```

The production app is not implemented yet. Start with the tickets in `docs/tickets/README.md`.

