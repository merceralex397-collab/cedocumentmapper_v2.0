import json
from pathlib import Path
import jsonschema
import pytest
from cedocumentmapper_v2.domain.models import (
    DocumentModel,
    DocumentPage,
    DocumentLine,
    FieldKey,
    FIELD_ORDER,
)

CONTRACTS_DIR = Path(__file__).parent.parent.parent / "docs" / "contracts"


def test_field_enum_and_order():
    """Ensure all FieldKeys are represented in FIELD_ORDER."""
    assert len(FieldKey) == len(FIELD_ORDER)
    for key in FieldKey:
        assert key in FIELD_ORDER


def test_eva_json_schema():
    """Ensure the final format example validates against eva-json.schema.json."""
    schema_path = CONTRACTS_DIR / "eva-json.schema.json"
    assert schema_path.exists()

    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)

    # Let's load the example JSON
    example_path = Path(__file__).parent.parent.parent.parent / "cedocumentmapper" / "docs" / "Final Format Example 02.json"
    if not example_path.exists():
        # Fallback to look relative to workspace
        example_path = Path("c:/Users/PC/Documents/GitHub/cedocumentmapper/docs/Final Format Example 02.json")
    
    assert example_path.exists(), f"Example JSON path not found: {example_path}"

    with open(example_path, "r", encoding="utf-8") as f:
        example_data = json.load(f)

    # Validate
    jsonschema.validate(instance=example_data, schema=schema)


def test_provider_config_schema():
    """Verify that provider config schema is a valid JSON schema."""
    schema_path = CONTRACTS_DIR / "provider-config.schema.json"
    assert schema_path.exists()

    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)

    # Simple validation using draft 2020-12
    jsonschema.Draft202012Validator.check_schema(schema)


def test_extraction_rule_schema():
    """Verify that extraction rule schema is a valid JSON schema."""
    schema_path = CONTRACTS_DIR / "extraction-rule.schema.json"
    assert schema_path.exists()

    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)

    jsonschema.Draft202012Validator.check_schema(schema)


def test_expected_fixture_schema():
    """Verify that expected fixture schema is a valid JSON schema."""
    schema_path = CONTRACTS_DIR / "expected-fixture.schema.json"
    assert schema_path.exists()

    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)

    jsonschema.Draft202012Validator.check_schema(schema)
