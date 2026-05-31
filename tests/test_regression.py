import os
import json
from pathlib import Path
import pytest
from jsonschema.validators import Draft202012Validator
from referencing import Registry, Resource

from cedocumentmapper_v2.readers import get_reader_for_path
from cedocumentmapper_v2.detection import ProviderDetector
from cedocumentmapper_v2.rules import RuleEngine
from cedocumentmapper_v2.config import migrate_providers_config

FIXTURES_DIR = Path(__file__).parent / "fixtures"
INSTRUCTIONS_DIR = FIXTURES_DIR / "instructions"
EXPECTED_DIR = FIXTURES_DIR / "expected"

V1_PROVIDERS_PATH = Path("c:/Users/PC/Documents/GitHub/cedocumentmapper/providers.json")
SCHEMA_PATH = Path(__file__).parent.parent / "docs" / "contracts" / "expected-fixture.schema.json"

def _load_validator() -> Draft202012Validator:
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema = json.load(f)
    # Registry setup
    schema_resource = Resource.from_contents(schema)
    registry = Registry().with_resource("https://collisionengineers.local/contracts/expected-fixture.schema.json", schema_resource)
    return Draft202012Validator(schema, registry=registry)

def _get_fixtures() -> list[tuple[Path, Path]]:
    if not INSTRUCTIONS_DIR.exists() or not EXPECTED_DIR.exists():
        return []
    
    fixtures = []
    for expected_file in EXPECTED_DIR.glob("*.expected.json"):
        # Load details
        try:
            with open(expected_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            src_name = data.get("source_file")
            if src_name:
                src_path = INSTRUCTIONS_DIR / src_name
                if src_path.exists():
                    fixtures.append((src_path, expected_file))
        except Exception:
            continue
    return fixtures

def test_expected_fixtures_schema():
    """Ensure all expected fixture JSONs are valid against the contract schema."""
    validator = _load_validator()
    fixtures = []
    if EXPECTED_DIR.exists():
        fixtures = list(EXPECTED_DIR.glob("*.expected.json"))
        
    for f_path in fixtures:
        with open(f_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        validator.validate(data)

def test_run_regression_fixtures():
    """Run extraction over fixtures and assert expected matches."""
    fixtures = _get_fixtures()
    if not fixtures:
        pytest.skip("No fixtures found to test regression.")
        
    # Load and migrate providers catalog
    assert V1_PROVIDERS_PATH.exists()
    with open(V1_PROVIDERS_PATH, "r", encoding="utf-8") as f:
        v1_data = json.load(f)
    v2_catalog = migrate_providers_config(v1_data)
    providers = v2_catalog["providers"]
    
    detector = ProviderDetector()
    rule_engine = RuleEngine()
    
    failures = []
    for src_path, expected_path in fixtures:
        with open(expected_path, "r", encoding="utf-8") as f:
            expected = json.load(f)
            
        # 1. Parse document
        reader = get_reader_for_path(src_path)
        doc = reader.read(src_path)
        
        # 2. Detect provider
        match = detector.detect(doc, providers)
        expected_prov_id = expected["expected_provider"]
        
        if match.provider_id != expected_prov_id:
            failures.append(
                f"Fixture {expected['fixture_id']}: expected provider '{expected_prov_id}', "
                f"but detected '{match.provider_id}'."
            )
            continue
            
        # Find provider config
        provider_cfg = next((p for p in providers if p["id"] == expected_prov_id), None)
        if not provider_cfg:
            failures.append(f"Fixture {expected['fixture_id']}: provider config '{expected_prov_id}' not found in catalog.")
            continue
            
        # 3. Extract record
        record = rule_engine.extract_record(doc, provider_cfg)
        
        # 4. Compare fields
        expected_values = expected["expected_values"]
        allowed_blanks = expected.get("allowed_blank_fields", [])
        
        field_diffs = []
        for field_name, expected_val in expected_values.items():
            ext_field = record.fields.get(field_name) # type: ignore
            actual_val = ext_field.value if ext_field else ""
            
            if actual_val != expected_val:
                if not actual_val and field_name in allowed_blanks:
                    continue
                field_diffs.append(
                    f"  Field '{field_name}': expected '{expected_val}', got '{actual_val}'"
                )
                
        if field_diffs:
            failures.append(
                f"Fixture {expected['fixture_id']} extraction mismatched:\n" + "\n".join(field_diffs)
            )
            
    if failures:
        pytest.fail("Regression tests failed:\n\n" + "\n\n".join(failures))
