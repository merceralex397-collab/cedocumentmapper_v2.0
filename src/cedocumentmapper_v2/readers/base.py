"""Reader interface contract."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from cedocumentmapper_v2.domain import DocumentModel


class DocumentReader(Protocol):
    supported_extensions: frozenset[str]

    def read(self, path: Path) -> DocumentModel:
        """Read a source document into the canonical document model."""

