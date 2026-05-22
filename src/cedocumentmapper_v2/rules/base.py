"""Rule interface contract."""

from __future__ import annotations

from typing import Protocol

from cedocumentmapper_v2.domain import DocumentModel, FieldExtraction


class ExtractionRule(Protocol):
    rule_id: str

    def extract(self, document: DocumentModel) -> FieldExtraction:
        """Extract one field value from a document."""

