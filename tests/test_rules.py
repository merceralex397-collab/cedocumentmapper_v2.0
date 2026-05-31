from pathlib import Path
from cedocumentmapper_v2.domain.models import DocumentModel, DocumentPage, DocumentLine, FieldKey
from cedocumentmapper_v2.rules import RuleEngine


def test_rule_label_same_line():
    lines = [
        DocumentLine(text="Vehicle Reg: AA11BBB", page_index=0, line_index=0),
    ]
    doc = DocumentModel(
        source_path=Path("dummy.pdf"),
        source_type="pdf",
        pages=(DocumentPage(page_index=0, lines=tuple(lines)),),
        plain_text="Vehicle Reg: AA11BBB",
    )

    engine = RuleEngine()
    rule = {
        "id": "vrm_rule",
        "kind": "label_same_line",
        "labels": ["Vehicle Reg"],
    }
    extracted = engine.extract_field(doc, FieldKey.VRM, rule)
    assert extracted.value == "AA11BBB"
    assert extracted.confidence == 1.0
    assert extracted.source_span.line_index == 0


def test_rule_label_same_line_fuzzy():
    lines = [
        DocumentLine(text="Vehcle Reglstratlon: AA11BBB", page_index=0, line_index=0),
    ]
    doc = DocumentModel(
        source_path=Path("dummy.pdf"),
        source_type="pdf",
        pages=(DocumentPage(page_index=0, lines=tuple(lines)),),
        plain_text="Vehcle Reglstratlon: AA11BBB",
    )

    engine = RuleEngine()
    rule = {
        "id": "vrm_rule",
        "kind": "label_same_line",
        "labels": ["Vehicle Registration"],
    }
    extracted = engine.extract_field(doc, FieldKey.VRM, rule)
    assert extracted.value == "AA11BBB"
    assert extracted.confidence >= 0.8  # Should fuzzy match
    assert extracted.source_span.line_index == 0


def test_rule_label_next_line():
    lines = [
        DocumentLine(text="Claimant Name", page_index=0, line_index=0),
        DocumentLine(text="John Smith", page_index=0, line_index=1),
    ]
    doc = DocumentModel(
        source_path=Path("dummy.pdf"),
        source_type="pdf",
        pages=(DocumentPage(page_index=0, lines=tuple(lines)),),
        plain_text="Claimant Name\nJohn Smith",
    )

    engine = RuleEngine()
    rule = {
        "id": "claimant_rule",
        "kind": "label_next_line",
        "labels": ["Claimant Name"],
    }
    extracted = engine.extract_field(doc, FieldKey.CLAIMANT_NAME, rule)
    assert extracted.value == "John Smith"
    assert extracted.source_span.line_index == 1


def test_rule_label_same_or_next_line_falls_back_to_next_line():
    lines = [
        DocumentLine(text="Claimant Name", page_index=0, line_index=0),
        DocumentLine(text="John Smith", page_index=0, line_index=1),
    ]
    doc = DocumentModel(
        source_path=Path("dummy.pdf"),
        source_type="pdf",
        pages=(DocumentPage(page_index=0, lines=tuple(lines)),),
        plain_text="Claimant Name\nJohn Smith",
    )

    engine = RuleEngine()
    rule = {
        "id": "claimant_rule",
        "kind": "label_same_or_next_line",
        "labels": ["Claimant Name"],
    }
    extracted = engine.extract_field(doc, FieldKey.CLAIMANT_NAME, rule)
    assert extracted.value == "John Smith"
    assert extracted.source_span.line_index == 1


def test_rule_between_labels():
    doc = DocumentModel(
        source_path=Path("dummy.pdf"),
        source_type="pdf",
        pages=(),
        plain_text="START_LABEL\nInner content to extract\nEND_LABEL",
    )

    engine = RuleEngine()
    rule = {
        "id": "between_rule",
        "kind": "between_labels",
        "start_label": "START_LABEL",
        "end_label": "END_LABEL",
    }
    extracted = engine.extract_field(doc, FieldKey.ACCIDENT_CIRCUMSTANCES, rule)
    assert extracted.value == "Inner content to extract"


def test_rule_fixed_line():
    lines = [
        DocumentLine(text="Line 1", page_index=0, line_index=0),
        DocumentLine(text="Target Line Text", page_index=0, line_index=1),
    ]
    doc = DocumentModel(
        source_path=Path("dummy.pdf"),
        source_type="pdf",
        pages=(DocumentPage(page_index=0, lines=tuple(lines)),),
        plain_text="Line 1\nTarget Line Text",
    )

    engine = RuleEngine()
    rule = {
        "id": "fixed_line_rule",
        "kind": "fixed_line",
        "line_number": 2,
    }
    extracted = engine.extract_field(doc, FieldKey.REFERENCE, rule)
    assert extracted.value == "Target Line Text"


def test_rule_fixed_line_range_uses_blank_preserving_raw_lines():
    lines = [
        DocumentLine(text="Line 1", page_index=0, line_index=0),
        DocumentLine(text="Target A", page_index=0, line_index=1),
        DocumentLine(text="Target B", page_index=0, line_index=2),
    ]
    doc = DocumentModel(
        source_path=Path("dummy.pdf"),
        source_type="pdf",
        pages=(DocumentPage(page_index=0, lines=tuple(lines)),),
        plain_text="Line 1\n\nTarget A\nTarget B",
        metadata={"raw_lines": ["Line 1", "", "Target A", "Target B"]},
    )

    engine = RuleEngine()
    rule = {
        "id": "fixed_range_rule",
        "kind": "fixed_line",
        "line_start": 3,
        "line_end": 4,
    }
    extracted = engine.extract_field(doc, FieldKey.INSPECTION_ADDRESS, rule)
    assert extracted.value == "Target A\nTarget B"


def test_rule_fixed_line_label():
    lines = [
        DocumentLine(text="Line 1", page_index=0, line_index=0),
        DocumentLine(text="Reference: SBL-12345", page_index=0, line_index=1),
    ]
    doc = DocumentModel(
        source_path=Path("dummy.pdf"),
        source_type="pdf",
        pages=(DocumentPage(page_index=0, lines=tuple(lines)),),
        plain_text="Line 1\nReference: SBL-12345",
    )

    engine = RuleEngine()
    rule = {
        "id": "fixed_line_label_rule",
        "kind": "fixed_line_label",
        "line_number": 2,
        "labels": ["Reference:"],
    }
    extracted = engine.extract_field(doc, FieldKey.REFERENCE, rule)
    assert extracted.value == "SBL-12345"


def test_rule_line_offset():
    lines = [
        DocumentLine(text="Find Me", page_index=0, line_index=0),
        DocumentLine(text="", page_index=0, line_index=1),
        DocumentLine(text="Target Value", page_index=0, line_index=2),
    ]
    doc = DocumentModel(
        source_path=Path("dummy.pdf"),
        source_type="pdf",
        pages=(DocumentPage(page_index=0, lines=tuple(lines)),),
        plain_text="Find Me\n\nTarget Value",
    )

    engine = RuleEngine()
    rule = {
        "id": "offset_rule",
        "kind": "line_offset",
        "labels": ["Find Me"],
        "offset": 1,
    }
    extracted = engine.extract_field(doc, FieldKey.REFERENCE, rule)
    assert extracted.value == "Target Value"
    assert extracted.source_span.line_index == 2


def test_rule_regex():
    doc = DocumentModel(
        source_path=Path("dummy.pdf"),
        source_type="pdf",
        pages=(),
        plain_text="Reference Number is REF-999-XYZ",
    )

    engine = RuleEngine()
    rule = {
        "id": "regex_rule",
        "kind": "regex",
        "pattern": r"REF-\d+-[A-Z]+",
    }
    extracted = engine.extract_field(doc, FieldKey.REFERENCE, rule)
    assert extracted.value == "REF-999-XYZ"


def test_rule_presence():
    doc = DocumentModel(
        source_path=Path("dummy.pdf"),
        source_type="pdf",
        pages=(),
        plain_text="The invoice contains VAT registration number.",
    )

    engine = RuleEngine()
    rule = {
        "id": "presence_rule",
        "kind": "presence",
        "tokens": ["vat number", "vat registration"],
        "value": "Yes",
    }
    extracted = engine.extract_field(doc, FieldKey.VAT_STATUS, rule)
    assert extracted.value == "Yes"


def test_rule_presence_absent_value():
    doc = DocumentModel(
        source_path=Path("dummy.pdf"),
        source_type="pdf",
        pages=(),
        plain_text="No tax marker here.",
    )

    engine = RuleEngine()
    rule = {
        "id": "presence_rule",
        "kind": "presence",
        "tokens": ["vat registration"],
        "value": "Yes",
        "absent_value": "No",
    }
    extracted = engine.extract_field(doc, FieldKey.VAT_STATUS, rule)
    assert extracted.value == "No"


def test_record_fallback_extracts_vrm_from_vehicle_context():
    lines = [
        DocumentLine(text="Vehicle Registration: AB12 CDE", page_index=0, line_index=0),
    ]
    doc = DocumentModel(
        source_path=Path("dummy.pdf"),
        source_type="pdf",
        pages=(DocumentPage(page_index=0, lines=tuple(lines)),),
        plain_text="Vehicle Registration: AB12 CDE",
    )

    engine = RuleEngine()
    record = engine.extract_record(doc, {"id": "p", "name": "Provider", "work_provider": "P", "field_rules": {}})
    assert record.fields[FieldKey.VRM].value == "AB12CDE"


def test_record_fallback_extracts_engineer_vehicle_model_from_exact_vehicle_label():
    lines = [
        DocumentLine(text="Vehicle: LEXUS NX 350H CVT", page_index=0, line_index=0),
        DocumentLine(text="Reg No: ML72YNF", page_index=0, line_index=1),
    ]
    doc = DocumentModel(
        source_path=Path("dummy.pdf"),
        source_type="pdf",
        pages=(DocumentPage(page_index=0, lines=tuple(lines)),),
        plain_text="\n".join(line.text for line in lines),
    )

    engine = RuleEngine()
    record = engine.extract_record(doc, {"id": "p", "name": "Provider", "work_provider": "P", "field_rules": {}})
    assert record.fields[FieldKey.VEHICLE_MODEL].value == "LEXUS NX 350H CVT"


def test_record_fallback_extracts_subject_reference_and_stops_address_at_contact_lines():
    lines = [
        DocumentLine(text="Subject: Kerr Brown Solicitors - Samual Stephen - AD/VRL/1/5241", page_index=0, line_index=0),
        DocumentLine(text="Client: Samual Stephen", page_index=0, line_index=1),
        DocumentLine(text="Address: 19A Garrier Road, Springside, Irvine, KA11 3AT", page_index=0, line_index=2),
        DocumentLine(text="Tele: 0781 086 5640", page_index=0, line_index=3),
        DocumentLine(text="Vehicle: Skoda Octavia", page_index=0, line_index=4),
        DocumentLine(text="Reg: YD72 KZX", page_index=0, line_index=5),
    ]
    doc = DocumentModel(
        source_path=Path("dummy.msg"),
        source_type="msg",
        pages=(DocumentPage(page_index=0, lines=tuple(lines)),),
        plain_text="\n".join(line.text for line in lines),
    )

    engine = RuleEngine()
    record = engine.extract_record(doc, {"id": "p", "name": "Provider", "work_provider": "P", "field_rules": {}})
    address = record.fields[FieldKey.INSPECTION_ADDRESS].value
    assert record.fields[FieldKey.REFERENCE].value == "AD/VRL/1/5241"
    assert "KA11 3AT" in address
    assert "Tele:" not in address
    assert "Vehicle:" not in address
    assert "Reg:" not in address


def test_record_fallback_recovers_oak_available_claimant_and_postcode_block():
    lines = [
        DocumentLine(text="Client reg: SG12 BLS", page_index=0, line_index=0),
        DocumentLine(text="The introducer is called Undent It.", page_index=0, line_index=1),
        DocumentLine(
            text="I have advised my client of your instruction. Please make arrangements for the inspection with my client. Mr Mohammad Butt is available at:",
            page_index=0,
            line_index=2,
        ),
        DocumentLine(text="Glasgow", page_index=0, line_index=3),
        DocumentLine(text="G53 7BB", page_index=0, line_index=4),
    ]
    doc = DocumentModel(
        source_path=Path("dummy.doc"),
        source_type="doc",
        pages=(DocumentPage(page_index=0, lines=tuple(lines)),),
        plain_text="\n".join(line.text for line in lines),
    )

    engine = RuleEngine()
    record = engine.extract_record(doc, {"id": "p", "name": "Provider", "work_provider": "P", "field_rules": {}})
    address = record.fields[FieldKey.INSPECTION_ADDRESS].value
    assert record.fields[FieldKey.CLAIMANT_NAME].value == "Mr Mohammad Butt"
    assert "Glasgow" in address
    assert "G53 7BB" in address
    assert "introducer" not in address.lower()


def test_rule_manual():
    doc = DocumentModel(source_path=Path("dummy.pdf"), source_type="pdf", pages=(), plain_text="")
    engine = RuleEngine()
    rule = {
        "id": "manual_rule",
        "kind": "manual",
        "value": "SBL Solicitors",
    }
    extracted = engine.extract_field(doc, FieldKey.WORK_PROVIDER, rule)
    assert extracted.value == "SBL Solicitors"


def test_rule_email_date():
    lines = [
        DocumentLine(text="Sent Date: 2026-05-31 16:57:31+01:00", page_index=0, line_index=0),
    ]
    doc = DocumentModel(
        source_path=Path("dummy.pdf"),
        source_type="pdf",
        pages=(DocumentPage(page_index=0, lines=tuple(lines)),),
        plain_text="Sent Date: 2026-05-31 16:57:31+01:00",
    )

    engine = RuleEngine()
    rule = {
        "id": "email_date_rule",
        "kind": "email_date",
        "labels": ["Sent Date:"],
    }
    extracted = engine.extract_field(doc, FieldKey.INSTRUCTION_DATE, rule)
    assert extracted.value == "31/05/2026"
