from __future__ import annotations

import re
from typing import Any
from cedocumentmapper_v2.domain.models import FieldKey


def clean_label_token(val: str) -> str:
    return val.replace("\r", "").replace("\n", "").strip()


def split_tokens(config_val: str) -> list[str]:
    if not config_val:
        return []
    return [clean_label_token(t) for t in config_val.split(",") if clean_label_token(t)]


def parse_two_label_config(config_value: str) -> tuple[str, str]:
    raw = (config_value or "").strip()
    if "||" in raw:
        start, end = raw.split("||", 1)
        return start.strip(), end.strip()
    parts = [part.strip() for part in raw.splitlines() if part.strip()]
    if len(parts) >= 2:
        return parts[0], parts[1]
    return "", ""


def migrate_provider(v1_prov: dict[str, Any]) -> dict[str, Any]:
    name = v1_prov.get("name", "Unknown")
    
    # Generate safe ID
    safe_id = re.sub(r"[^a-z0-9_-]+", "", name.lower().replace(" ", "_"))
    if not safe_id or not safe_id[0].isalnum():
        safe_id = "p_" + safe_id if safe_id else "provider"
    
    v1_rules = v1_prov.get("field_rules", {})
    
    # Retrieve work_provider from rules
    wp_rule = v1_rules.get("work_provider", {})
    work_provider = wp_rule.get("config", "").strip()
    if not work_provider:
        work_provider = name

    # Detect phrases
    detect_phrases = v1_prov.get("detect_phrases", [])
    detect = {
        "required_phrases": [str(p).strip() for p in detect_phrases if str(p).strip()],
        "optional_phrases": [],
        "negative_phrases": [],
        "minimum_confidence": 0.75,
    }

    # Field rules migration
    field_rules = {}
    for key_str, v1_rule in v1_rules.items():
        try:
            field_key = FieldKey(key_str)
        except ValueError:
            # Skip unknown fields, but they will be kept in metadata
            continue

        method = v1_rule.get("method", "single_label")
        config = v1_rule.get("config", "")
        
        # Translate rule kinds
        kind = "label_same_line"
        rule_data: dict[str, Any] = {"id": f"{safe_id}_{key_str}"}

        # Handle presence checks for vat_status & mileage_unit
        if field_key in {FieldKey.VAT_STATUS, FieldKey.MILEAGE_UNIT}:
            kind = "presence"
            rule_data["tokens"] = split_tokens(config)
            if field_key == FieldKey.VAT_STATUS:
                rule_data["value"] = "Yes"
                rule_data["absent_value"] = "No"
            else:
                # If Km/km is mentioned in config, default unit to Km, else Miles
                rule_data["value"] = "Km" if "km" in config.lower() else "Miles"
                rule_data["absent_value"] = "Miles" if rule_data["value"] == "Km" else "Km"
        else:
            if method in {"single_label", "labels", "multiline_labels"}:
                kind = "label_same_or_next_line" if method == "single_label" else "label_same_line"
                rule_data["labels"] = split_tokens(config)
            elif method == "two_labels":
                kind = "between_labels"
                start, end = parse_two_label_config(config)
                rule_data["start_label"] = start
                rule_data["end_label"] = end
            elif method == "fixed_position":
                kind = "fixed_line"
                raw_pos = config.strip()
                range_match = re.match(r"^(\d+)\s*-\s*(\d+)", raw_pos)
                if range_match:
                    rule_data["line_start"] = int(range_match.group(1))
                    rule_data["line_end"] = int(range_match.group(2))
                else:
                    try:
                        match = re.match(r"^(\d+)", raw_pos)
                        rule_data["line_number"] = int(match.group(1)) if match else 1
                    except Exception:
                        rule_data["line_number"] = 1
            elif method == "fixed_position_label":
                kind = "fixed_line_label"
                line_part, label = parse_two_label_config(config)
                try:
                    rule_data["line_number"] = int(line_part)
                except Exception:
                    rule_data["line_number"] = 1
                rule_data["labels"] = [label] if label else []
            elif method == "single_label_offset":
                kind = "line_offset"
                label, offset_part = parse_two_label_config(config)
                rule_data["labels"] = [label] if label else []
                # Parse offset
                m = re.fullmatch(r"\s*([+\-])\s*(\d+)\s*", offset_part)
                if m:
                    sign = m.group(1)
                    magnitude = int(m.group(2))
                    rule_data["offset"] = magnitude if sign == "+" else -magnitude
                else:
                    rule_data["offset"] = 0
            elif method == "email_date":
                kind = "email_date"
                rule_data["labels"] = [config.strip()] if config.strip() else []
            elif method in {"manual_input", "fixed_value"}:
                kind = "manual"
                rule_data["value"] = config.strip()
            else:
                # Fallback
                kind = "label_same_line"
                rule_data["labels"] = split_tokens(config)

        rule_data["kind"] = kind
        field_rules[key_str] = rule_data

    # Build migrated provider
    migrated = {
        "id": safe_id,
        "name": name,
        "work_provider": work_provider,
        "enabled": True,
        "priority": 0,
        "detect": detect,
        "field_rules": field_rules,
    }

    # Preserve v1 provider fields as user data. Known booleans stay at root for
    # compatibility, and any unknown keys are kept under metadata.v1_unknown.
    for opt in ["engineer_report", "use_current_date_for_inspection_date", "force_postcode_for_inspection_address"]:
        if opt in v1_prov:
            migrated[opt] = v1_prov[opt]

    known_keys = {"name", "field_rules", "detect_phrases", "engineer_report", "use_current_date_for_inspection_date", "force_postcode_for_inspection_address"}
    unknown = {k: v for k, v in v1_prov.items() if k not in known_keys}
    if unknown:
        migrated["metadata"] = {"v1_unknown": unknown}

    return migrated


def migrate_providers_config(v1_data: dict[str, Any]) -> dict[str, Any]:
    v2_providers = []
    for prov in v1_data.get("providers", []):
        v2_providers.append(migrate_provider(prov))

    return {
        "schema_version": 2,
        "providers": v2_providers,
    }
