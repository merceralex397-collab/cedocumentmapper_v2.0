from cedocumentmapper_v2.domain.models import FieldKey
from cedocumentmapper_v2.normalization import (
    normalize_vrm,
    normalize_mileage,
    normalize_date,
    normalize_vat_status,
    normalize_mileage_unit,
    normalize_address,
    validate_fields,
)


def test_normalize_vrm():
    assert normalize_vrm("  rj62 rtu ") == "RJ62RTU"
    assert normalize_vrm("AA 11 BBB") == "AA11BBB"


def test_normalize_mileage():
    assert normalize_mileage("  28,487 Miles") == "28487"
    assert normalize_mileage("Speedo: 12345km") == "12345"
    assert normalize_mileage("no number") == ""


def test_normalize_date():
    assert normalize_date("27th April 2026") == "27/04/2026"
    assert normalize_date("21 Apr 2026") == "21/04/2026"
    assert normalize_date("April 27 2026") == "27/04/2026"
    assert normalize_date("2026-05-31") == "31/05/2026"
    assert normalize_date("invalid date") == "invalid date"  # Returns original if fails


def test_normalize_vat_status():
    assert normalize_vat_status("yes") == "Yes"
    assert normalize_vat_status("No") == "No"
    assert normalize_vat_status("") == ""
    assert normalize_vat_status("gibberish") == "gibberish"


def test_normalize_mileage_unit():
    assert normalize_mileage_unit("miles") == "Miles"
    assert normalize_mileage_unit("km") == "Km"
    assert normalize_mileage_unit("M") == "Miles"
    assert normalize_mileage_unit("") == ""


def test_normalize_address():
    # Empty case should return 6 blank lines
    assert normalize_address("") == "\n\n\n\n\n"

    # Multi-line with postcode
    address_in = "Somstar Recovery\nSomstar House\nBirmingham\nB5 6JX"
    expected = "Somstar Recovery\nSomstar House\nBirmingham\n\n\nB5 6JX"
    assert normalize_address(address_in) == expected

    # Long address overflow to line 5
    long_address = "Line1\nLine2\nLine3\nLine4\nLine5\nLine6\nB5 6JX"
    expected_long = "Line1\nLine2\nLine3\nLine4\nLine5 Line6\nB5 6JX"
    assert normalize_address(long_address) == expected_long


def test_validation():
    # Test valid fields (should have no issues)
    fields = {
        FieldKey.WORK_PROVIDER: "SBL",
        FieldKey.VRM: "RJ62RTU",
        FieldKey.VEHICLE_MODEL: "Skoda Superb",
        FieldKey.CLAIMANT_NAME: "Mr Piotr Robaczkiewicz",
        FieldKey.REFERENCE: "SBL-12345",
        FieldKey.INCIDENT_DATE: "14/04/2026",
        FieldKey.INSTRUCTION_DATE: "15/04/2026",
        FieldKey.INSPECTION_DATE: "15/04/2026",
        FieldKey.INSPECTION_ADDRESS: "123 Street\n\n\n\n\nB5 6JX",
        FieldKey.VAT_STATUS: "No",
        FieldKey.MILEAGE: "53600",
        FieldKey.MILEAGE_UNIT: "Km",
    }
    issues = validate_fields(fields)
    assert len(issues) == 0

    # Test missing required field
    bad_fields = fields.copy()
    bad_fields[FieldKey.VRM] = ""
    issues = validate_fields(bad_fields)
    assert len(issues) == 1
    assert issues[0].severity == "error"
    assert issues[0].field == FieldKey.VRM

    # Test invalid date
    bad_fields2 = fields.copy()
    bad_fields2[FieldKey.INCIDENT_DATE] = "14-04-2026"
    issues = validate_fields(bad_fields2)
    assert len(issues) == 1
    assert issues[0].severity == "warning"
    assert issues[0].field == FieldKey.INCIDENT_DATE
