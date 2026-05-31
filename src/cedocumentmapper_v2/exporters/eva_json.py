from __future__ import annotations

import json
from pathlib import Path
import jsonschema

from cedocumentmapper_v2.domain.models import ExtractedRecord, FieldKey, FIELD_ORDER, FIELD_LABELS
from cedocumentmapper_v2.exporters.base import Exporter


class EVAJsonExporter(Exporter):
    def __init__(self, schema_path: Path | None = None):
        if schema_path is None:
            # Default schema path resolution
            self.schema_path = Path(__file__).parent.parent.parent / "docs" / "contracts" / "eva-json.schema.json"
        else:
            self.schema_path = schema_path

    def export(self, record: ExtractedRecord) -> str:
        """Serialize record fields into an ordered EVA JSON string."""
        # Work Provider is required to be non-empty for JSON export
        wp_val = record.fields.get(FieldKey.WORK_PROVIDER)
        if not wp_val or not wp_val.value.strip():
            raise ValueError("Export blocked: 'Work Provider' cannot be blank.")

        # Construct dictionary in specific display field order
        export_data = {}
        for key in FIELD_ORDER:
            label = FIELD_LABELS[key]
            val = record.fields.get(key)
            export_data[label] = val.value if val else ""

        # Validate against schema
        if self.schema_path.exists():
            with open(self.schema_path, "r", encoding="utf-8") as f:
                schema = json.load(f)
            jsonschema.validate(instance=export_data, schema=schema)

        # Output indented ordered JSON
        return json.dumps(export_data, indent=2, ensure_ascii=False)
