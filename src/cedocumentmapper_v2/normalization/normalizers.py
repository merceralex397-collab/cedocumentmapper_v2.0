from __future__ import annotations

import re
from datetime import datetime
from cedocumentmapper_v2.domain.models import FieldKey, ExtractionIssue


def normalize_vrm(value: str) -> str:
    """Normalize extracted VRMs by removing all whitespace and uppercasing."""
    return re.sub(r"\s+", "", (value or "").strip()).upper()


def normalize_mileage(value: str) -> str:
    """Extract a mileage number from the text.
    
    Collects digits and commas, and stops at the first non-digit/non-comma.
    """
    raw = (value or "").strip()
    if not raw:
        return ""

    digits = []
    started = False
    for ch in raw:
        if ch.isdigit():
            digits.append(ch)
            started = True
            continue
        if started:
            if ch == ",":
                continue
            break
    return "".join(digits)


def normalize_date(value: str) -> str:
    """Convert a date string into DD/MM/YYYY form."""
    raw = (value or "").strip()
    if not raw:
        return ""

    cleaned = re.sub(r"(\d+)\s*(st|nd|rd|th)\b", r"\1", raw, flags=re.IGNORECASE)
    cleaned = re.sub(r"^[^\dA-Za-z]+", "", cleaned)
    cleaned = re.sub(r"(\d{1,2}/\d{2})(\d{4})\b", r"\1/\2", cleaned)
    cleaned = cleaned.replace(",", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    formats = [
        "%d/%m/%Y",
        "%d/%m/%y",
        "%d-%m-%Y",
        "%d-%m-%y",
        "%d-%b-%Y",
        "%d-%b-%y",
        "%d-%B-%Y",
        "%d-%B-%y",
        "%d %B %Y",
        "%d %b %Y",
        "%B %d %Y",
        "%b %d %Y",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(cleaned, fmt)
            return dt.strftime("%d/%m/%Y")
        except ValueError:
            continue
    return raw


def normalize_vat_status(value: str) -> str:
    """Normalize VAT status to Yes/No/blank."""
    lowered = (value or "").strip().lower()
    if not lowered:
        return ""
    if lowered in {"yes", "y", "true", "1"}:
        return "Yes"
    if lowered in {"no", "n", "false", "0"}:
        return "No"
    return value.strip()


def normalize_mileage_unit(value: str) -> str:
    """Normalize mileage unit to Miles/Km/blank."""
    lowered = (value or "").strip().lower()
    if not lowered:
        return ""
    if "mile" in lowered or "mi" in lowered or lowered == "m":
        return "Miles"
    if "km" in lowered or "kilometer" in lowered or "kilometre" in lowered:
        return "Km"
    return value.strip()


def normalize_address(value: str, force_postcode: bool = False) -> str:
    """Normalise the inspection address to a 6-line canonical form."""
    text = (value or "").strip()
    if not text:
        return "\n".join([""] * 6)

    def _canonicalise_postcode(postcode_text: str) -> str:
        compact = re.sub(r"\s+", "", (postcode_text or "").upper())
        if len(compact) < 5:
            return ""
        return f"{compact[:-3]} {compact[-3:]}"

    postcode_anywhere_re = re.compile(
        r"\b([A-Z]{1,2}\d[A-Z\d]?\s*\d[ABD-HJLNP-UW-Z]{2})\b", re.IGNORECASE
    )
    postcode_end_re = re.compile(
        r"\b([A-Z]{1,2}\d[A-Z\d]?\s*\d[ABD-HJLNP-UW-Z]{2})\b\s*$", re.IGNORECASE
    )

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\s*,\s*", "\n", text)
    raw_lines = [part.strip() for part in text.splitlines() if part.strip()]
    if not raw_lines:
        return "\n".join([""] * 6)

    postcode_line = ""
    body_lines = []

    if len(raw_lines) == 1:
        single_line = raw_lines[0]
        if force_postcode:
            end_match = postcode_end_re.search(single_line)
            if end_match:
                postcode_line = _canonicalise_postcode(end_match.group(1))
                remainder = single_line[:end_match.start()].strip(" ,")
                body_lines = [remainder] if remainder else []
            else:
                anywhere_match = postcode_anywhere_re.search(single_line)
                if anywhere_match:
                    postcode_line = _canonicalise_postcode(anywhere_match.group(1))
                    pre = single_line[:anywhere_match.start()].strip(" ,")
                    body_lines = [pre] if pre else []
                else:
                    body_lines = raw_lines[:]
        else:
            body_lines = raw_lines[:]
    else:
        last_line = raw_lines[-1]
        any_match = postcode_anywhere_re.search(last_line)
        if any_match:
            postcode_line = _canonicalise_postcode(any_match.group(1))
            body_lines = raw_lines[:-1]
        else:
            postcode_line = last_line
            body_lines = raw_lines[:-1]

    if len(body_lines) >= 5:
        line1 = body_lines[0]
        line2 = body_lines[1] if len(body_lines) > 1 else ""
        line3 = body_lines[2] if len(body_lines) > 2 else ""
        line4 = body_lines[3] if len(body_lines) > 3 else ""
        overflow = [part for part in body_lines[4:] if part]
        line5 = " ".join(overflow)
        normalized = [line1, line2, line3, line4, line5, postcode_line]
    else:
        body_lines = body_lines[:5]
        normalized = body_lines + [""] * (5 - len(body_lines)) + [postcode_line]

    normalized = [part.strip() for part in normalized[:6]]
    while len(normalized) < 6:
        normalized.append("")
    return "\n".join(normalized)


def validate_fields(fields: dict[FieldKey, str]) -> list[ExtractionIssue]:
    """Validate all field values, generating warnings and errors."""
    issues = []

    # 1. Required Fields Check
    required_keys = {
        FieldKey.WORK_PROVIDER,
        FieldKey.VRM,
        FieldKey.VEHICLE_MODEL,
        FieldKey.CLAIMANT_NAME,
        FieldKey.REFERENCE,
        FieldKey.INCIDENT_DATE,
        FieldKey.INSTRUCTION_DATE,
    }
    for req_key in required_keys:
        val = fields.get(req_key, "").strip()
        if not val:
            issues.append(
                ExtractionIssue(
                    field=req_key,
                    severity="error",
                    code="missing_required_field",
                    message=f"Required field '{req_key.value}' is empty.",
                )
            )

    # 2. Date Format Check
    date_keys = {FieldKey.INCIDENT_DATE, FieldKey.INSTRUCTION_DATE, FieldKey.INSPECTION_DATE}
    for date_key in date_keys:
        val = fields.get(date_key, "").strip()
        if val:
            # Must be DD/MM/YYYY
            try:
                datetime.strptime(val, "%d/%m/%Y")
            except ValueError:
                issues.append(
                    ExtractionIssue(
                        field=date_key,
                        severity="warning",
                        code="invalid_date_format",
                        message=f"Date '{val}' is not in DD/MM/YYYY format.",
                    )
                )

    # 3. VRM Check (UK format check)
    vrm = fields.get(FieldKey.VRM, "").strip()
    if vrm:
        vrm_clean = normalize_vrm(vrm)
        # Check standard UK format or standard lengths (2-7 alphanumeric characters)
        if not re.match(r"^[A-Z0-9]{2,8}$", vrm_clean):
            issues.append(
                ExtractionIssue(
                    field=FieldKey.VRM,
                    severity="warning",
                    code="invalid_vrm",
                    message=f"VRM '{vrm}' does not look like a valid registration mark.",
                )
            )

    # 4. Mileage Check
    mileage = fields.get(FieldKey.MILEAGE, "").strip()
    if mileage and not mileage.isdigit():
        issues.append(
            ExtractionIssue(
                field=FieldKey.MILEAGE,
                severity="warning",
                code="invalid_mileage",
                message=f"Mileage '{mileage}' must contain digits only.",
            )
        )

    # 5. VAT Status Check
    vat = fields.get(FieldKey.VAT_STATUS, "").strip()
    if vat and vat not in {"Yes", "No"}:
        issues.append(
            ExtractionIssue(
                field=FieldKey.VAT_STATUS,
                severity="warning",
                code="invalid_vat",
                message=f"VAT Status '{vat}' should be 'Yes' or 'No'.",
            )
        )

    # 6. Mileage Unit Check
    unit = fields.get(FieldKey.MILEAGE_UNIT, "").strip()
    if unit and unit not in {"Miles", "Km"}:
        issues.append(
            ExtractionIssue(
                field=FieldKey.MILEAGE_UNIT,
                severity="warning",
                code="invalid_mileage_unit",
                message=f"Mileage Unit '{unit}' should be 'Miles' or 'Km'.",
            )
        )

    return issues
