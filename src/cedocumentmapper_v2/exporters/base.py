from __future__ import annotations

from typing import Protocol
from cedocumentmapper_v2.domain.models import ExtractedRecord


class Exporter(Protocol):
    def export(self, record: ExtractedRecord) -> str | bytes:
        """Export a reviewed record to a serialized string or bytes representation."""
        ...
