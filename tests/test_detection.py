from pathlib import Path
from cedocumentmapper_v2.domain.models import DocumentModel, DocumentPage, DocumentLine
from cedocumentmapper_v2.detection import ProviderDetector


def test_detector_basic():
    doc = DocumentModel(
        source_path=Path("dummy.pdf"),
        source_type="pdf",
        pages=(),
        plain_text="Hello World, this is an ALISON claim document.",
    )

    providers = [
        {
            "id": "alison",
            "name": "Alison Solicitors",
            "enabled": True,
            "detect": {
                "required_phrases": ["ALISON", "claim"],
                "optional_phrases": ["solicitors"],
                "negative_phrases": ["REJECT"],
            },
        }
    ]

    detector = ProviderDetector()
    match = detector.detect(doc, providers)
    assert match.provider_id == "alison"
    # Base confidence 0.8 because "solicitors" optional phrase is missing
    assert match.confidence == 0.8
    assert "ALISON" in match.matched_terms


def test_detector_optional_phrases():
    doc = DocumentModel(
        source_path=Path("dummy.pdf"),
        source_type="pdf",
        pages=(),
        plain_text="Hello World, this is an ALISON claim document for Solicitors.",
    )

    providers = [
        {
            "id": "alison",
            "name": "Alison Solicitors",
            "enabled": True,
            "detect": {
                "required_phrases": ["ALISON", "claim"],
                "optional_phrases": ["solicitors"],
            },
        }
    ]

    detector = ProviderDetector()
    match = detector.detect(doc, providers)
    assert match.provider_id == "alison"
    # Confidence should be 1.0 because optional phrase matched
    assert match.confidence == 1.0


def test_detector_negative_phrases():
    doc = DocumentModel(
        source_path=Path("dummy.pdf"),
        source_type="pdf",
        pages=(),
        plain_text="Hello World, this is an ALISON claim document but we REJECT this.",
    )

    providers = [
        {
            "id": "alison",
            "name": "Alison Solicitors",
            "enabled": True,
            "detect": {
                "required_phrases": ["ALISON", "claim"],
                "negative_phrases": ["REJECT"],
            },
        }
    ]

    detector = ProviderDetector()
    match = detector.detect(doc, providers)
    assert match.provider_id is None  # Should not match


def test_detector_tie_break():
    doc = DocumentModel(
        source_path=Path("dummy.pdf"),
        source_type="pdf",
        pages=(),
        plain_text="Hello World, this has phrase_a and phrase_b.",
    )

    providers = [
        {
            "id": "prov_1",
            "name": "Provider 1",
            "priority": 0,
            "detect": {
                "required_phrases": ["phrase_a"],
            },
        },
        {
            "id": "prov_2",
            "name": "Provider 2",
            "priority": 1,  # Higher priority should win
            "detect": {
                "required_phrases": ["phrase_a"],
            },
        },
    ]

    detector = ProviderDetector()
    match = detector.detect(doc, providers)
    assert match.provider_id == "prov_2"
