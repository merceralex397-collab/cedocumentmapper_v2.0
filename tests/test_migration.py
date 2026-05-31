import json
from pathlib import Path
from jsonschema.validators import Draft202012Validator  # type: ignore
from referencing import Registry, Resource  # type: ignore
from cedocumentmapper_v2.config import migrate_providers_config

V1_PROVIDERS_PATH = Path("c:/Users/PC/Documents/GitHub/cedocumentmapper/providers.json")
V2_SCHEMA_PATH = Path(__file__).parent.parent / "docs" / "contracts" / "provider-config.schema.json"


def test_migration_and_validation():
    assert V1_PROVIDERS_PATH.exists()
    assert V2_SCHEMA_PATH.exists()

    with open(V1_PROVIDERS_PATH, "r", encoding="utf-8") as f:
        v1_data = json.load(f)

    # Perform migration
    v2_data = migrate_providers_config(v1_data)

    # Check structure
    assert v2_data["schema_version"] == 2
    assert len(v2_data["providers"]) > 0

    # Ensure each has expected attributes
    first = v2_data["providers"][0]
    assert "id" in first
    assert "name" in first
    assert "work_provider" in first
    assert "detect" in first
    assert "field_rules" in first

    # Validate against v2 JSON schema without making network calls
    with open(V2_SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema = json.load(f)

    # Load referenced schema
    ref_schema_path = V2_SCHEMA_PATH.parent / "extraction-rule.schema.json"
    with open(ref_schema_path, "r", encoding="utf-8") as f:
        ref_schema = json.load(f)

    # Construct modern Registry resources
    schema_resource = Resource.from_contents(schema)
    ref_resource = Resource.from_contents(ref_schema)

    registry = Registry().with_resources([
        ("https://collisionengineers.local/contracts/provider-config.schema.json", schema_resource),
        ("https://collisionengineers.local/contracts/extraction-rule.schema.json", ref_resource),
    ])

    # Validate
    validator = Draft202012Validator(schema, registry=registry)
    validator.validate(v2_data)
