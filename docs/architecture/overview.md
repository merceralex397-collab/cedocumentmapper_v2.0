# Architecture Overview

## Pipeline

```text
Source file
  -> Reader
  -> DocumentModel
  -> Provider detection
  -> Rule engine
  -> Field normalizers
  -> Validation
  -> Review UI
  -> EVA JSON export
```

## Core Change from v1

Version 1 applies provider rules mostly to raw extracted text. Version 2 introduces a canonical document model so rules can use text, line order, page number, and coordinates where available.

## Module Responsibilities

- Readers turn files into `DocumentModel`.
- Detection chooses a provider and explains why.
- Rules extract raw values with source spans.
- Normalizers convert raw values into EVA-ready values.
- Validators flag missing or suspicious values.
- UI displays the record, diagnostics, source preview, and rule setup.
- Exporters serialize only validated/reviewed values.

## Reliability Strategy

The regression corpus is the product safety net. Every known provider format should have a fixture with expected field values. Reader and rule changes are acceptable only when fixture diffs are understood.

