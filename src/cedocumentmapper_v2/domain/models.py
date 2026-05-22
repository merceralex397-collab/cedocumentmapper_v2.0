"""Core domain models.

These dataclasses are the Python-side contract for v2. Implementation modules
should depend on these shapes instead of exchanging raw strings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal


class FieldKey(StrEnum):
    WORK_PROVIDER = "work_provider"
    VRM = "vrm"
    VEHICLE_MODEL = "vehicle_model"
    CLAIMANT_NAME = "claimant_name"
    REFERENCE = "reference"
    INCIDENT_DATE = "incident_date"
    INSTRUCTION_DATE = "instruction_date"
    INSPECTION_DATE = "inspection_date"
    INSPECTION_ADDRESS = "inspection_address"
    ACCIDENT_CIRCUMSTANCES = "accident_circumstances"
    VAT_STATUS = "vat_status"
    MILEAGE = "mileage"
    MILEAGE_UNIT = "mileage_unit"


FIELD_ORDER: tuple[FieldKey, ...] = (
    FieldKey.WORK_PROVIDER,
    FieldKey.VRM,
    FieldKey.VEHICLE_MODEL,
    FieldKey.CLAIMANT_NAME,
    FieldKey.REFERENCE,
    FieldKey.INCIDENT_DATE,
    FieldKey.INSTRUCTION_DATE,
    FieldKey.INSPECTION_DATE,
    FieldKey.INSPECTION_ADDRESS,
    FieldKey.ACCIDENT_CIRCUMSTANCES,
    FieldKey.VAT_STATUS,
    FieldKey.MILEAGE,
    FieldKey.MILEAGE_UNIT,
)

FIELD_LABELS: dict[FieldKey, str] = {
    FieldKey.WORK_PROVIDER: "Work Provider",
    FieldKey.VRM: "VRM",
    FieldKey.VEHICLE_MODEL: "Vehicle Model",
    FieldKey.CLAIMANT_NAME: "Claimant Name",
    FieldKey.REFERENCE: "Reference",
    FieldKey.INCIDENT_DATE: "Incident Date",
    FieldKey.INSTRUCTION_DATE: "Instruction Date",
    FieldKey.INSPECTION_DATE: "Inspection Date",
    FieldKey.INSPECTION_ADDRESS: "Inspection Address",
    FieldKey.ACCIDENT_CIRCUMSTANCES: "Accident Circumstances",
    FieldKey.VAT_STATUS: "VAT Status",
    FieldKey.MILEAGE: "Mileage",
    FieldKey.MILEAGE_UNIT: "Mileage Unit",
}

REQUIRED_FIELDS: frozenset[FieldKey] = frozenset(
    {
        FieldKey.WORK_PROVIDER,
        FieldKey.VRM,
        FieldKey.VEHICLE_MODEL,
        FieldKey.CLAIMANT_NAME,
        FieldKey.REFERENCE,
        FieldKey.INCIDENT_DATE,
        FieldKey.INSTRUCTION_DATE,
    }
)


@dataclass(frozen=True)
class SourceSpan:
    page_index: int | None = None
    line_index: int | None = None
    bbox: tuple[float, float, float, float] | None = None


@dataclass(frozen=True)
class DocumentLine:
    text: str
    page_index: int
    line_index: int
    bbox: tuple[float, float, float, float] | None = None
    block_id: str | None = None
    confidence: float | None = None


@dataclass(frozen=True)
class DocumentPage:
    page_index: int
    width: float | None = None
    height: float | None = None
    lines: tuple[DocumentLine, ...] = ()


@dataclass(frozen=True)
class DocumentModel:
    source_path: Path
    source_type: Literal["pdf", "docx", "doc", "eml", "msg", "txt"]
    pages: tuple[DocumentPage, ...]
    plain_text: str
    reader_notes: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderMatch:
    provider_id: str | None
    provider_name: str
    confidence: float
    matched_terms: tuple[str, ...] = ()
    missing_terms: tuple[str, ...] = ()
    rejected_terms: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExtractionIssue:
    field: FieldKey | None
    severity: Literal["info", "warning", "error"]
    code: str
    message: str


@dataclass(frozen=True)
class FieldExtraction:
    value: str
    raw_value: str = ""
    rule_id: str | None = None
    confidence: float | None = None
    source_span: SourceSpan | None = None
    issues: tuple[ExtractionIssue, ...] = ()


@dataclass(frozen=True)
class ExtractedRecord:
    provider: ProviderMatch
    fields: dict[FieldKey, FieldExtraction]
    issues: tuple[ExtractionIssue, ...] = ()

