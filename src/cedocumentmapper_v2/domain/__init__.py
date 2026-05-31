"""Domain contracts shared by readers, rules, normalizers, exporters, and UI."""

from .models import (
    DocumentLine,
    DocumentModel,
    DocumentPage,
    ExtractedRecord,
    FieldExtraction,
    SourceSpan,
    ExtractionIssue,
    FieldKey,
    ProviderMatch,
    REQUIRED_FIELDS,
)

__all__ = [
    "DocumentLine",
    "DocumentModel",
    "DocumentPage",
    "ExtractedRecord",
    "FieldExtraction",
    "SourceSpan",
    "ExtractionIssue",
    "FieldKey",
    "ProviderMatch",
    "REQUIRED_FIELDS",
]

