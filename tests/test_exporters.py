import json
import pytest
from cedocumentmapper_v2.domain.models import ExtractedRecord, ProviderMatch, FieldKey, FieldExtraction
from cedocumentmapper_v2.exporters import EVAJsonExporter, RJSDocxExporter


def test_eva_json_exporter():
    # Prepare ExtractedRecord
    fields = {
        FieldKey.WORK_PROVIDER: FieldExtraction(value="SBL"),
        FieldKey.VRM: FieldExtraction(value="RJ62RTU"),
        FieldKey.VEHICLE_MODEL: FieldExtraction(value="Skoda Superb"),
        FieldKey.CLAIMANT_NAME: FieldExtraction(value="Mr Piotr Robaczkiewicz"),
        FieldKey.REFERENCE: FieldExtraction(value="SBL-12345"),
        FieldKey.INCIDENT_DATE: FieldExtraction(value="14/04/2026"),
        FieldKey.INSTRUCTION_DATE: FieldExtraction(value="15/04/2026"),
        FieldKey.INSPECTION_DATE: FieldExtraction(value="15/04/2026"),
        FieldKey.INSPECTION_ADDRESS: FieldExtraction(value="123 Street\n\n\n\n\nB5 6JX"),
        FieldKey.VAT_STATUS: FieldExtraction(value="No"),
        FieldKey.MILEAGE: FieldExtraction(value="53600"),
        FieldKey.MILEAGE_UNIT: FieldExtraction(value="Km"),
        FieldKey.ACCIDENT_CIRCUMSTANCES: FieldExtraction(value="Parked vehicle hit"),
    }
    
    record = ExtractedRecord(
        provider=ProviderMatch(provider_id="sbl", provider_name="SBL Solicitors", confidence=1.0),
        fields=fields,
    )

    exporter = EVAJsonExporter()
    exported_str = exporter.export(record)
    
    # Check it parses as JSON and contains required keys
    data = json.loads(exported_str)
    assert data["Work Provider"] == "SBL"
    assert data["VRM"] == "RJ62RTU"
    assert data["VAT Status"] == "No"
    
    # Assert correct display order
    keys = list(data.keys())
    assert keys[0] == "Work Provider"
    assert keys[1] == "VRM"
    assert keys[12] == "Mileage Unit"


def test_eva_json_exporter_blocks_blank_work_provider():
    # Prepare record with empty work provider
    fields = {
        FieldKey.WORK_PROVIDER: FieldExtraction(value=""),
        FieldKey.VRM: FieldExtraction(value="RJ62RTU"),
    }
    record = ExtractedRecord(
        provider=ProviderMatch(provider_id="sbl", provider_name="SBL Solicitors", confidence=1.0),
        fields=fields,
    )

    exporter = EVAJsonExporter()
    with pytest.raises(ValueError, match="Export blocked: 'Work Provider' cannot be blank."):
        exporter.export(record)


def test_rjs_docx_exporter():
    fields = {
        FieldKey.WORK_PROVIDER: FieldExtraction(value="RJS"),
        FieldKey.VRM: FieldExtraction(value="RJ62RTU"),
        FieldKey.VEHICLE_MODEL: FieldExtraction(value="Skoda Superb"),
        FieldKey.CLAIMANT_NAME: FieldExtraction(value="Mr Piotr Robaczkiewicz"),
        FieldKey.REFERENCE: FieldExtraction(value="RJS-12345"),
        FieldKey.INCIDENT_DATE: FieldExtraction(value="14/04/2026"),
        FieldKey.INSTRUCTION_DATE: FieldExtraction(value="15/04/2026"),
        FieldKey.INSPECTION_ADDRESS: FieldExtraction(value="123 Street\n\nB5 6JX"),
    }
    record = ExtractedRecord(
        provider=ProviderMatch(provider_id="rjs", provider_name="RJS Solicitors", confidence=1.0),
        fields=fields,
    )

    exporter = RJSDocxExporter()
    docx_bytes = exporter.export(record)
    assert isinstance(docx_bytes, bytes)
    assert len(docx_bytes) > 0
