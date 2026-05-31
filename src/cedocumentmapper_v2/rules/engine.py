from __future__ import annotations

import difflib
import re
from datetime import datetime
from dataclasses import replace
from typing import Any
from cedocumentmapper_v2.domain.models import (
    DocumentModel,
    DocumentLine,
    FieldExtraction,
    SourceSpan,
    ExtractionIssue,
    FieldKey,
    ExtractedRecord,
    ProviderMatch,
    FIELD_ORDER,
)
from cedocumentmapper_v2.normalization import (
    normalize_vrm,
    normalize_mileage,
    normalize_date,
    normalize_vat_status,
    normalize_mileage_unit,
    normalize_address,
    validate_fields,
)


def clean_val(value: str) -> str:
    """Clean a value matching v1 clean_value."""
    value = value.replace("\xa0", " ").replace("\u00a0", " ")
    value = value.replace("\r", " ").replace("\t", " ")
    value = re.sub(r"[ ]{2,}", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip(" :\n")


def fuzzy_find_label(lines: list[DocumentLine], label: str, threshold: float = 0.8) -> tuple[int, DocumentLine, float] | None:
    """Search for a label in document lines, supporting exact, substring, and fuzzy matching.
    
    Returns (line_idx, DocumentLine, confidence) if found, otherwise None.
    """
    target = label.lower().strip()
    
    # 1. Exact or substring match (1.0 confidence)
    for idx, line in enumerate(lines):
        line_txt = line.text.lower().strip()
        if target in line_txt or line_txt == target or line_txt.rstrip(":") == target:
            return idx, line, 1.0

    # 2. Fuzzy match using SequenceMatcher
    effective_threshold = max(threshold, 0.85) if len(target) < 15 else threshold
    best_ratio = 0.0
    best_match = None
    for idx, line in enumerate(lines):
        line_txt = line.text.lower().strip()
        # Slide a window of length target over line_txt if line_txt is longer
        if len(line_txt) > len(target) + 5:
            # Check substrings of similar length
            words = line_txt.split()
            target_words_len = len(target.split())
            for i in range(len(words) - target_words_len + 1):
                sub = " ".join(words[i:i + target_words_len])
                ratio = difflib.SequenceMatcher(None, target, sub).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_match = (idx, line)
        else:
            ratio = difflib.SequenceMatcher(None, target, line_txt).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = (idx, line)

    if best_ratio >= effective_threshold and best_match is not None:
        return best_match[0], best_match[1], best_ratio

    return None


UK_POSTCODE_RE = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[ABD-HJLNP-UW-Z]{2}\b", re.IGNORECASE)
DATE_RE = re.compile(
    r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}(?:st|nd|rd|th)?\s+"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{2,4}|"
    r"\d{4}-\d{1,2}-\d{1,2})\b",
    re.IGNORECASE,
)
VRM_RE = re.compile(
    r"\b(?!VAT\b)(?!TEL\b)(?!REF\b)([A-Z]{2}\d{2}\s?[A-Z]{3}|[A-Z]\d{1,3}\s?[A-Z]{3}|"
    r"[A-Z]{3}\s?\d{1,3}[A-Z]?|[A-Z]{1,3}\s?\d{1,4})\b",
    re.IGNORECASE,
)


class RuleEngine:
    def extract_record(
        self, document: DocumentModel, provider: dict[str, Any]
    ) -> ExtractedRecord:
        """Apply all configured rules in provider config to a DocumentModel.
        
        Runs extraction, normalizes results, applies conditional overrides,
        and runs cross-field validation to build the ExtractedRecord.
        """
        fields: dict[FieldKey, FieldExtraction] = {}
        field_rules = provider.get("field_rules", {})
        
        use_current_date = provider.get("use_current_date_for_inspection_date", False)
        force_postcode = provider.get("force_postcode_for_inspection_address", False)
        
        for field_key in FIELD_ORDER:
            key_str = field_key.value
            rule_cfg = field_rules.get(key_str)
            
            # Default empty extraction
            ext = FieldExtraction(value="", raw_value="")
            
            if rule_cfg:
                ext = self.extract_field(document, field_key, rule_cfg)

            if not ext.value:
                fallback = self._fallback_field(document, field_key)
                if fallback.value:
                    fallback_norm = fallback.value
                    if field_key == FieldKey.VRM:
                        fallback_norm = normalize_vrm(fallback_norm)
                    elif field_key == FieldKey.MILEAGE:
                        fallback_norm = normalize_mileage(fallback_norm)
                    elif field_key in {FieldKey.INCIDENT_DATE, FieldKey.INSTRUCTION_DATE, FieldKey.INSPECTION_DATE}:
                        fallback_norm = normalize_date(fallback_norm)
                    elif field_key == FieldKey.VAT_STATUS:
                        fallback_norm = normalize_vat_status(fallback_norm)
                    elif field_key == FieldKey.MILEAGE_UNIT:
                        fallback_norm = normalize_mileage_unit(fallback_norm)
                    elif field_key == FieldKey.INSPECTION_ADDRESS:
                        fallback_norm = normalize_address(fallback_norm, force_postcode=force_postcode)
                    
                    if not self._is_suspicious_value(field_key, fallback_norm, document):
                        ext = fallback
            
            # Normalise the value
            norm_val = ext.value
            if field_key == FieldKey.VRM:
                norm_val = normalize_vrm(norm_val)
            elif field_key == FieldKey.MILEAGE:
                norm_val = normalize_mileage(norm_val)
            elif field_key in {FieldKey.INCIDENT_DATE, FieldKey.INSTRUCTION_DATE, FieldKey.INSPECTION_DATE}:
                norm_val = normalize_date(norm_val)
            elif field_key == FieldKey.VAT_STATUS:
                norm_val = normalize_vat_status(norm_val)
            elif field_key == FieldKey.MILEAGE_UNIT:
                norm_val = normalize_mileage_unit(norm_val)
            elif field_key == FieldKey.INSPECTION_ADDRESS:
                norm_val = normalize_address(norm_val, force_postcode=force_postcode)

            if self._is_suspicious_value(field_key, norm_val, document):
                fallback = self._fallback_field(document, field_key)
                fallback_norm = fallback.value
                if field_key == FieldKey.VRM:
                    fallback_norm = normalize_vrm(fallback_norm)
                elif field_key == FieldKey.MILEAGE:
                    fallback_norm = normalize_mileage(fallback_norm)
                elif field_key in {FieldKey.INCIDENT_DATE, FieldKey.INSTRUCTION_DATE, FieldKey.INSPECTION_DATE}:
                    fallback_norm = normalize_date(fallback_norm)
                elif field_key == FieldKey.VAT_STATUS:
                    fallback_norm = normalize_vat_status(fallback_norm)
                elif field_key == FieldKey.MILEAGE_UNIT:
                    fallback_norm = normalize_mileage_unit(fallback_norm)
                elif field_key == FieldKey.INSPECTION_ADDRESS:
                    fallback_norm = normalize_address(fallback_norm, force_postcode=force_postcode)
                if fallback_norm and not self._is_suspicious_value(field_key, fallback_norm, document):
                    ext = fallback
                    norm_val = fallback_norm
                elif field_key in {
                    FieldKey.VRM,
                    FieldKey.VEHICLE_MODEL,
                    FieldKey.CLAIMANT_NAME,
                    FieldKey.REFERENCE,
                    FieldKey.INSPECTION_ADDRESS,
                }:
                    ext = replace(ext, value="", raw_value=ext.raw_value)
                    norm_val = ""
            
            # Apply conditional/fallback rules
            if field_key == FieldKey.WORK_PROVIDER and not norm_val:
                norm_val = provider.get("work_provider", "").strip() or provider.get("name", "").strip()
            
            if field_key == FieldKey.INSPECTION_DATE and use_current_date:
                norm_val = datetime.now().strftime("%d/%m/%Y")
            
            # Update the extraction object with the normalized value
            ext_normalized = FieldExtraction(
                value=norm_val,
                raw_value=ext.raw_value,
                rule_id=ext.rule_id,
                confidence=ext.confidence,
                source_span=ext.source_span,
                issues=ext.issues
            )
            fields[field_key] = ext_normalized
            
        # Compile plain text fields for validation
        fields_str_map = {k: v.value for k, v in fields.items()}
        validation_issues = validate_fields(fields_str_map)
        
        # Attach issues to specific fields or to the record
        record_issues = []
        for issue in validation_issues:
            if issue.field and issue.field in fields:
                f_ext = fields[issue.field]
                fields[issue.field] = FieldExtraction(
                    value=f_ext.value,
                    raw_value=f_ext.raw_value,
                    rule_id=f_ext.rule_id,
                    confidence=f_ext.confidence,
                    source_span=f_ext.source_span,
                    issues=f_ext.issues + (issue,)
                )
            else:
                record_issues.append(issue)
                
        provider_match = ProviderMatch(
            provider_id=provider.get("id"),
            provider_name=provider.get("name", "Unknown"),
            confidence=1.0,
            matched_terms=(),
            missing_terms=(),
            rejected_terms=()
        )
        
        return ExtractedRecord(
            provider=provider_match,
            fields=fields,
            issues=tuple(record_issues)
        )

    def extract_field(
        self, document: DocumentModel, field_key: FieldKey, rule_config: dict[str, Any]
    ) -> FieldExtraction:
        """Apply a single rule config to a DocumentModel."""
        rule_id = rule_config.get("id", "default")
        kind = rule_config.get("kind", "label_same_line")
        
        # Aggregate all lines across pages into a flat list for line-based operations
        flat_lines: list[DocumentLine] = []
        for page in document.pages:
            flat_lines.extend(page.lines)
        raw_lines = self._raw_lines(document, flat_lines)

        try:
            if kind == "label_same_line":
                return self._extract_label_same_line(flat_lines, rule_config, rule_id)
            elif kind == "label_next_line":
                return self._extract_label_next_line(flat_lines, rule_config, rule_id)
            elif kind == "label_same_or_next_line":
                return self._extract_label_same_or_next_line(flat_lines, rule_config, rule_id)
            elif kind == "between_labels":
                return self._extract_between_labels(flat_lines, document.plain_text, rule_config, rule_id)
            elif kind == "fixed_line":
                return self._extract_fixed_line(flat_lines, raw_lines, rule_config, rule_id)
            elif kind == "fixed_line_label":
                return self._extract_fixed_line_label(flat_lines, rule_config, rule_id)
            elif kind == "line_offset":
                return self._extract_line_offset(flat_lines, rule_config, rule_id)
            elif kind == "regex":
                return self._extract_regex(document.plain_text, rule_config, rule_id)
            elif kind == "presence":
                return self._extract_presence(document.plain_text, rule_config, rule_id)
            elif kind == "manual":
                return self._extract_manual(rule_config, rule_id)
            elif kind == "email_date":
                return self._extract_email_date(flat_lines, rule_config, rule_id)
            else:
                return FieldExtraction(
                    value="",
                    issues=(ExtractionIssue(
                        field=field_key,
                        severity="error",
                        code="invalid_rule_kind",
                        message=f"Unknown rule kind: {kind}",
                    ),),
                )
        except Exception as exc:
            return FieldExtraction(
                value="",
                issues=(ExtractionIssue(
                    field=field_key,
                    severity="error",
                    code="extraction_failure",
                    message=f"Rule extraction crashed: {exc}",
                ),),
            )

    def _extract_label_same_line(self, lines: list[DocumentLine], cfg: dict[str, Any], rule_id: str) -> FieldExtraction:
        labels = cfg.get("labels", [])
        for label in labels:
            res = fuzzy_find_label(lines, label)
            if res:
                idx, line, conf = res
                line_txt = line.text
                
                # Check for standard delimiters first on the line to see if we can cleanly split it.
                # E.g., "Vehcle Reglstratlon: AA11BBB" -> split by ":"
                split_success = False
                for sep in (":", "|"):
                    if sep in line_txt:
                        parts = line_txt.split(sep, 1)
                        left_part = parts[0].strip()
                        # If the left part fuzzy matches our label, the right part is the value!
                        # Compare using difflib
                        ratio = difflib.SequenceMatcher(None, label.lower().strip(), left_part.lower().strip()).ratio()
                        if ratio >= 0.7:
                            val = clean_val(parts[1])
                            return FieldExtraction(
                                value=val,
                                raw_value=val,
                                rule_id=rule_id,
                                confidence=max(conf, ratio),
                                source_span=SourceSpan(page_index=line.page_index, line_index=line.line_index, bbox=line.bbox),
                            )
                dash_match = re.search(r"\s[-–—]\s", line_txt)
                if dash_match:
                    left_part = line_txt[:dash_match.start()].strip()
                    ratio = difflib.SequenceMatcher(None, label.lower().strip(), left_part.lower().strip()).ratio()
                    if ratio >= 0.7:
                        val = clean_val(line_txt[dash_match.end():])
                        return FieldExtraction(
                            value=val,
                            raw_value=val,
                            rule_id=rule_id,
                            confidence=max(conf, ratio),
                            source_span=SourceSpan(page_index=line.page_index, line_index=line.line_index, bbox=line.bbox),
                        )
                
                # If no split worked, try exact substring match
                lbl_idx = line_txt.lower().find(label.lower())
                if lbl_idx >= 0:
                    val = clean_val(line_txt[lbl_idx + len(label):])
                else:
                    # Let's find the best matching substring using SequenceMatcher get_matching_blocks
                    s = difflib.SequenceMatcher(None, label.lower(), line_txt.lower())
                    matching_blocks = s.get_matching_blocks()
                    if matching_blocks:
                        # Find the end of the last matched block to slice after it
                        last_block = max(matching_blocks, key=lambda b: b.b)
                        end_idx = last_block.b + last_block.size
                        val = clean_val(line_txt[end_idx:])
                    else:
                        val = clean_val(line_txt)
                
                if val:
                    return FieldExtraction(
                        value=val,
                        raw_value=val,
                        rule_id=rule_id,
                        confidence=conf,
                        source_span=SourceSpan(page_index=line.page_index, line_index=line.line_index, bbox=line.bbox),
                    )
        return FieldExtraction(value="", rule_id=rule_id)

    def _extract_label_next_line(self, lines: list[DocumentLine], cfg: dict[str, Any], rule_id: str) -> FieldExtraction:
        labels = cfg.get("labels", [])
        for label in labels:
            res = fuzzy_find_label(lines, label)
            if res:
                idx, line, conf = res
                # Find the next non-empty line
                for next_line in lines[idx + 1:]:
                    val = clean_val(next_line.text)
                    if val and not self._is_label_only_value(val):
                        return FieldExtraction(
                            value=val,
                            raw_value=val,
                            rule_id=rule_id,
                            confidence=conf,
                            source_span=SourceSpan(page_index=next_line.page_index, line_index=next_line.line_index, bbox=next_line.bbox),
                        )
        return FieldExtraction(value="", rule_id=rule_id)

    def _extract_label_same_or_next_line(self, lines: list[DocumentLine], cfg: dict[str, Any], rule_id: str) -> FieldExtraction:
        same_line = self._extract_label_same_line(lines, cfg, rule_id)
        if same_line.value:
            return same_line
        return self._extract_label_next_line(lines, cfg, rule_id)

    def _extract_between_labels(self, lines: list[DocumentLine], plain_text: str, cfg: dict[str, Any], rule_id: str) -> FieldExtraction:
        start_label = cfg.get("start_label", "")
        end_label = cfg.get("end_label", "")
        if not start_label or not end_label:
            return FieldExtraction(value="", rule_id=rule_id)

        # Regex search first
        pattern = re.compile(rf"(?is){re.escape(start_label)}\s*:?\s*(.*?)\s*(?={re.escape(end_label)})")
        match = pattern.search(plain_text)
        if match:
            val = clean_val(match.group(1))
            if val:
                return FieldExtraction(value=val, raw_value=val, rule_id=rule_id, confidence=1.0)

        # Iterate lines fallback
        capture = False
        collected = []
        source_span = None
        for line in lines:
            line_txt = line.text
            lower = line_txt.lower().strip()
            if not capture:
                if lower.startswith(start_label.lower()):
                    capture = True
                    remainder = clean_val(re.sub(rf"(?i)^{re.escape(start_label)}\s*:?", "", line_txt))
                    if remainder:
                        collected.append(remainder)
                    source_span = SourceSpan(page_index=line.page_index, line_index=line.line_index, bbox=line.bbox)
            else:
                if lower.startswith(end_label.lower()):
                    break
                collected.append(clean_val(line_txt))

        val = clean_val("\n".join(c for c in collected if c))
        return FieldExtraction(
            value=val,
            raw_value=val,
            rule_id=rule_id,
            confidence=1.0 if val else 0.0,
            source_span=source_span,
        )

    def _extract_fixed_line(self, lines: list[DocumentLine], raw_lines: list[str], cfg: dict[str, Any], rule_id: str) -> FieldExtraction:
        start = cfg.get("line_start")
        end = cfg.get("line_end")
        if start and end:
            first = max(int(start), 1)
            last = max(int(end), first)
            source = raw_lines if raw_lines else [line.text for line in lines]
            selected = [clean_val(line) for line in source[first - 1:last] if clean_val(line)]
            val = clean_val("\n".join(selected))
            span_line = lines[min(first - 1, len(lines) - 1)] if lines else None
            return FieldExtraction(
                value=val,
                raw_value=val,
                rule_id=rule_id,
                confidence=1.0 if val else 0.0,
                source_span=SourceSpan(page_index=span_line.page_index, line_index=span_line.line_index, bbox=span_line.bbox) if span_line else None,
            )

        line_no = cfg.get("line_number")
        if not line_no or line_no <= 0 or line_no > len(lines):
            return FieldExtraction(value="", rule_id=rule_id)

        line = lines[line_no - 1]
        val = clean_val(line.text)
        return FieldExtraction(
            value=val,
            raw_value=val,
            rule_id=rule_id,
            confidence=1.0,
            source_span=SourceSpan(page_index=line.page_index, line_index=line.line_index, bbox=line.bbox),
        )

    def _extract_fixed_line_label(self, lines: list[DocumentLine], cfg: dict[str, Any], rule_id: str) -> FieldExtraction:
        line_no = cfg.get("line_number")
        labels = cfg.get("labels", [])
        if not line_no or line_no <= 0 or line_no > len(lines) or not labels:
            return FieldExtraction(value="", rule_id=rule_id)

        line = lines[line_no - 1]
        line_txt = line.text
        for label in labels:
            idx = line_txt.lower().find(label.lower())
            if idx >= 0:
                after = clean_val(line_txt[idx + len(label):])
                return FieldExtraction(
                    value=after,
                    raw_value=after,
                    rule_id=rule_id,
                    confidence=1.0,
                    source_span=SourceSpan(page_index=line.page_index, line_index=line.line_index, bbox=line.bbox),
                )
        return FieldExtraction(value="", rule_id=rule_id)

    def _extract_line_offset(self, lines: list[DocumentLine], cfg: dict[str, Any], rule_id: str) -> FieldExtraction:
        labels = cfg.get("labels", [])
        offset = cfg.get("offset", 0)

        for label in labels:
            res = fuzzy_find_label(lines, label)
            if res:
                anchor_idx, anchor_line, conf = res
                if offset == 0:
                    val = clean_val(anchor_line.text)
                    return FieldExtraction(
                        value=val,
                        raw_value=val,
                        rule_id=rule_id,
                        confidence=conf,
                        source_span=SourceSpan(page_index=anchor_line.page_index, line_index=anchor_line.line_index, bbox=anchor_line.bbox),
                    )

                step = 1 if offset > 0 else -1
                steps_remaining = abs(offset)
                i = anchor_idx + step
                last_seen = anchor_idx

                while 0 <= i < len(lines) and steps_remaining > 0:
                    if clean_val(lines[i].text):
                        last_seen = i
                        steps_remaining -= 1
                        if steps_remaining == 0:
                            break
                    i += step
                
                target_line = lines[last_seen]
                val = clean_val(target_line.text)
                return FieldExtraction(
                    value=val,
                    raw_value=val,
                    rule_id=rule_id,
                    confidence=conf,
                    source_span=SourceSpan(page_index=target_line.page_index, line_index=target_line.line_index, bbox=target_line.bbox),
                )
        return FieldExtraction(value="", rule_id=rule_id)

    def _extract_regex(self, plain_text: str, cfg: dict[str, Any], rule_id: str) -> FieldExtraction:
        pattern_str = cfg.get("pattern", "")
        if not pattern_str:
            return FieldExtraction(value="", rule_id=rule_id)

        try:
            pattern = re.compile(pattern_str, re.IGNORECASE | re.MULTILINE)
        except re.error as err:
            raise ValueError(f"Invalid regex pattern '{pattern_str}': {err}")

        match = pattern.search(plain_text)
        if match:
            # If there are groups, take the first one; else take the whole match
            val = clean_val(match.group(1) if match.groups() else match.group(0))
            return FieldExtraction(value=val, raw_value=val, rule_id=rule_id, confidence=1.0)
        return FieldExtraction(value="", rule_id=rule_id)

    def _extract_presence(self, plain_text: str, cfg: dict[str, Any], rule_id: str) -> FieldExtraction:
        tokens = cfg.get("tokens", [])
        value_if_present = cfg.get("value", "Yes")
        value_if_absent = cfg.get("absent_value", "")
        
        if not tokens:
            return FieldExtraction(value="", rule_id=rule_id)

        haystack = plain_text.lower()
        for token in tokens:
            needle = token.lower().strip()
            if needle and needle in haystack:
                return FieldExtraction(value=value_if_present, raw_value=value_if_present, rule_id=rule_id, confidence=1.0)
        
        return FieldExtraction(value=value_if_absent, raw_value=value_if_absent, rule_id=rule_id, confidence=1.0)

    def _extract_manual(self, cfg: dict[str, Any], rule_id: str) -> FieldExtraction:
        val = cfg.get("value", "").strip()
        if val.lower() == "{today}":
            val = datetime.now().strftime("%d/%m/%Y")
        return FieldExtraction(value=val, raw_value=val, rule_id=rule_id, confidence=1.0)

    def _extract_email_date(self, lines: list[DocumentLine], cfg: dict[str, Any], rule_id: str) -> FieldExtraction:
        labels = cfg.get("labels", [])
        date_re = re.compile(r"\b(\d{4}-\d{1,2}-\d{1,2})\b")

        for label in labels:
            res = fuzzy_find_label(lines, label)
            if res:
                idx, line, conf = res
                line_txt = line.text
                lbl_idx = line_txt.lower().find(label.lower())
                if lbl_idx >= 0:
                    tail = line_txt[lbl_idx + len(label):]
                else:
                    tail = line_txt
                
                match = date_re.search(tail)
                if match:
                    iso = match.group(1)
                    try:
                        dt = datetime.strptime(iso, "%Y-%m-%d")
                        val = dt.strftime("%d/%m/%Y")
                        return FieldExtraction(
                            value=val,
                            raw_value=val,
                            rule_id=rule_id,
                            confidence=conf,
                            source_span=SourceSpan(page_index=line.page_index, line_index=line.line_index, bbox=line.bbox),
                        )
                    except ValueError:
                        continue
        return FieldExtraction(value="", rule_id=rule_id)

    def _raw_lines(self, document: DocumentModel, lines: list[DocumentLine]) -> list[str]:
        metadata_lines = document.metadata.get("raw_lines") if isinstance(document.metadata, dict) else None
        if isinstance(metadata_lines, list) and all(isinstance(line, str) for line in metadata_lines):
            return metadata_lines
        if document.plain_text:
            return document.plain_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        return [line.text for line in lines]

    def _is_label_only_value(self, value: str) -> bool:
        cleaned = clean_val(value).lower().strip(" :")
        return cleaned in {
            "name",
            "model",
            "make/model",
            "make",
            "vehicle",
            "registration",
            "reg",
            "reference",
            "ref",
            "date",
            "client",
            "claimant",
            "our client",
            "our insured",
            "your ref",
            "our ref",
            "post code",
            "postcode",
            ":",
        }

    def _is_suspicious_value(self, field_key: FieldKey, value: str, document: DocumentModel) -> bool:
        cleaned = clean_val(value)
        lower = cleaned.lower()
        if field_key not in {FieldKey.ACCIDENT_CIRCUMSTANCES, FieldKey.INSPECTION_ADDRESS}:
            salutations = {
                "yours faithfully",
                "yours sincerely",
                "dear sirs",
                "dear sir",
                "dear mr",
                "dear ms",
                "dear miss",
                "dear mrs",
                "solicitors limited",
                "baker & coleman",
            }
            if any(s in lower for s in salutations):
                return True
        if field_key in {FieldKey.INCIDENT_DATE, FieldKey.INSTRUCTION_DATE, FieldKey.INSPECTION_DATE}:
            return bool(cleaned) and not re.fullmatch(r"\d{2}/\d{2}/\d{4}", cleaned)
        if field_key == FieldKey.CLAIMANT_NAME:
            if len(cleaned) > 40:
                return True
            if any(w in f" {lower} " for w in (" was ", " has ", " had ", " been ", " when ", " hit ", " that ", " this ", " inspect ", " report ", " parked ", " vehicle ", " accident ", " witness ", " seen ", " collision ")):
                return True
            return (
                self._is_label_only_value(cleaned)
                or bool(re.fullmatch(r"[A-Z]{1,3}\d{1,3}\s?[A-Z]{3}", cleaned, re.IGNORECASE))
                or any(
                    phrase in lower
                    for phrase in ("accident:", "client:", "stationary at", "proceedings ", "defendant", "claimant was")
                )
            )
        if field_key == FieldKey.VEHICLE_MODEL:
            if len(cleaned) > 40:
                if any(w in lower for w in ("grateful", "arrange", "inspect", "forward", "report", "locate", "address", "accident", "loss", "collision")):
                    return True
            vrm_match = self._fallback_vrm_from_labels([line for page in document.pages for line in page.lines])
            vrm = normalize_vrm(vrm_match.value) if vrm_match.value else ""
            return (
                self._is_label_only_value(cleaned)
                or cleaned in {",", ".", "-"}
                or len(cleaned) <= 1
                or (vrm and vrm in normalize_vrm(cleaned))
                or any(
                    phrase in lower
                    for phrase in (
                        "please",
                        "accident",
                        "claimant",
                        "defendant",
                        "currently located",
                        "vehicle is currently located",
                        "introducer",
                        " is called ",
                        "source:",
                        "provide a report",
                        "report detailing",
                        "costs of repair",
                        "cost of replacement",
                    )
                )
            )
        if field_key == FieldKey.VRM:
            compact = normalize_vrm(cleaned)
            if not compact:
                return False
            if len(compact) < 5 and not re.fullmatch(r"[A-Z]{1,3}\d{1,3}[A-Z]{1,3}", compact):
                return True
            postcode_context = re.search(rf"\b{re.escape(cleaned)}\s*\d[A-Z]{{2}}\b", document.plain_text, re.IGNORECASE)
            return bool(postcode_context)
        if field_key == FieldKey.REFERENCE:
            if len(cleaned) > 35:
                return True
            if any(w in f" {lower} " for w in (" once ", " available ", " choose ", " report ", " inspect ", " vehicle ", " accident ", " loss ", " lose ")):
                return True
            return (
                self._is_label_only_value(cleaned)
                or bool(re.fullmatch(r"[A-Za-z!?]{1,10}", cleaned))
                or "proclaim" in lower
                or "sign off" in lower
                or "engineers report" in lower
                or "please " in lower
                or "before preparing" in lower
                or "your reports" in lower
                or "electronic basis" in lower
                or "report and fee" in lower
            )
        if field_key == FieldKey.INSPECTION_ADDRESS:
            return self._address_contains_narrative(cleaned)
        return False

    def _address_contains_narrative(self, value: str) -> bool:
        lower = clean_val(value).lower()
        return any(
            phrase in lower
            for phrase in (
                "introducer",
                "i have advised",
                "please make arrangements",
                "please arrange",
                "provide a report",
                "recovery of damages",
                "circumstances of the accident",
                "\ntele:",
                "\ntel:",
                "\nmobile",
                "\nvehicle:",
                "\nreg:",
            )
        )

    def _fallback_field(self, document: DocumentModel, field_key: FieldKey) -> FieldExtraction:
        lines: list[DocumentLine] = []
        for page in document.pages:
            lines.extend(page.lines)
        text = document.plain_text or "\n".join(line.text for line in lines)
        lowered = text.lower()

        if field_key == FieldKey.VRM:
            return self._fallback_vrm(lines, text)
        if field_key == FieldKey.REFERENCE:
            return self._fallback_reference(lines)
        if field_key == FieldKey.CLAIMANT_NAME:
            claimant = self._fallback_claimant_name(lines)
            if claimant.value:
                return claimant
            return self._fallback_label_value(
                lines,
                ("our insured", "our client", "client name", "claimant name", "policyholder", "client", "claimant", "name"),
                field_key,
                reject_labels={"name", "claimant", "client", "claimant name"},
            )
        if field_key == FieldKey.VEHICLE_MODEL:
            model = self._fallback_vehicle_model(lines)
            if model.value:
                return model
            return self._fallback_label_value(
                lines,
                ("vehicle model", "make/model", "make and model", "our client's vehicle", "our clients vehicle", "client vehicle", "vehicle make", "make", "model"),
                field_key,
                reject_labels={"model", "vehicle model", "make/model"},
            )
        if field_key == FieldKey.INSPECTION_ADDRESS:
            return self._fallback_address(lines)
        if field_key == FieldKey.INCIDENT_DATE:
            return self._fallback_context_date(lines, ("accident", "incident", "rta", "collision", "loss"), field_key)
        if field_key == FieldKey.INSTRUCTION_DATE:
            return self._fallback_context_date(lines, ("instruct", "received", "sent", "date"), field_key)
        if field_key == FieldKey.VAT_STATUS and "vat" in lowered:
            if re.search(r"\b(no|not|non)\s+vat\b|vat\s+(?:no|not|none|exempt)", lowered):
                return FieldExtraction(value="No", raw_value="No", rule_id="fallback_vat_negative", confidence=0.65)
            return FieldExtraction(value="Yes", raw_value="Yes", rule_id="fallback_vat_positive", confidence=0.55)
        if field_key == FieldKey.MILEAGE_UNIT:
            if re.search(r"\b(km|kilomet(?:er|re)s?)\b", lowered):
                return FieldExtraction(value="Km", raw_value="Km", rule_id="fallback_mileage_unit", confidence=0.6)
            if re.search(r"\b(miles?|mi)\b", lowered):
                return FieldExtraction(value="Miles", raw_value="Miles", rule_id="fallback_mileage_unit", confidence=0.6)
        return FieldExtraction(value="", rule_id=f"fallback_{field_key.value}", confidence=0.0)

    def _fallback_label_value(
        self,
        lines: list[DocumentLine],
        labels: tuple[str, ...],
        field_key: FieldKey,
        reject_labels: set[str] | None = None,
    ) -> FieldExtraction:
        reject_labels = reject_labels or set()
        for label in labels:
            res = fuzzy_find_label(lines, label, threshold=0.72)
            if not res:
                continue
            idx, line, conf = res
            local_cfg = {"labels": [label]}
            same = self._extract_label_same_line(lines, local_cfg, f"fallback_{field_key.value}")
            if same.value and self._is_rejected_label_value(same.value, reject_labels):
                return FieldExtraction(value="", rule_id=f"fallback_{field_key.value}", confidence=0.0)
            candidates = [same.value] if same.value else []
            for next_line in lines[idx + 1:idx + 4]:
                value = clean_val(next_line.text)
                if value and not self._is_label_only_value(value):
                    candidates.append(value)
            for value in candidates:
                if self._is_rejected_label_value(value, reject_labels):
                    continue
                return FieldExtraction(
                    value=value,
                    raw_value=value,
                    rule_id=f"fallback_{field_key.value}",
                    confidence=min(0.9, conf * 0.85),
                    source_span=SourceSpan(page_index=line.page_index, line_index=line.line_index, bbox=line.bbox),
                )
        return FieldExtraction(value="", rule_id=f"fallback_{field_key.value}", confidence=0.0)

    def _is_rejected_label_value(self, value: str, reject_labels: set[str]) -> bool:
        cleaned = clean_val(value).lower().strip(" :")
        if not cleaned or cleaned in reject_labels:
            return True
        if len(cleaned) <= 2:
            return True
        return False

    def _normalized_label_text(self, value: str) -> str:
        value = value.lower().replace("’", "'")
        value = re.sub(r"[^a-z0-9]+", " ", value)
        return re.sub(r"\s+", " ", value).strip()

    def _extract_value_after_structured_label(
        self,
        lines: list[DocumentLine],
        label_options: tuple[str, ...],
        rule_id: str,
        reject_labels: set[str] | None = None,
    ) -> FieldExtraction:
        normalized_options = [self._normalized_label_text(label) for label in label_options]
        reject_labels = reject_labels or set()
        for idx, line in enumerate(lines):
            normalized_line = self._normalized_label_text(line.text)
            matched_option = next(
                (
                    option
                    for option in normalized_options
                    if option
                    and (
                        option in normalized_line
                        if len(option.split()) > 1
                        else normalized_line == option or normalized_line.startswith(option + " ")
                    )
                ),
                "",
            )
            if not matched_option:
                continue
            same = ""
            if ":" in line.text:
                same = clean_val(line.text.rsplit(":", 1)[1])
            else:
                words = matched_option.split()
                parts = clean_val(line.text).split()
                if len(parts) > len(words):
                    same = clean_val(" ".join(parts[len(words):]))
            candidates = [same] if same and same != clean_val(line.text) else []
            if not same or self._is_label_only_value(same):
                for next_line in lines[idx + 1:idx + 5]:
                    value = clean_val(next_line.text)
                    if value and not self._is_label_only_value(value):
                        candidates.append(value)
            for value in candidates:
                if self._is_rejected_label_value(value, reject_labels):
                    continue
                return FieldExtraction(
                    value=value,
                    raw_value=value,
                    rule_id=rule_id,
                    confidence=0.86,
                    source_span=SourceSpan(page_index=line.page_index, line_index=line.line_index, bbox=line.bbox),
                )
        return FieldExtraction(value="", rule_id=rule_id, confidence=0.0)

    def _fallback_claimant_name(self, lines: list[DocumentLine]) -> FieldExtraction:
        structured = self._extract_value_after_structured_label(
            lines,
            ("our insured", "our client", "re client", "client"),
            "fallback_claimant_structured",
            reject_labels={"name", "client", "our client", "claimant"},
        )
        if structured.value and not re.fullmatch(r"[A-Z]{1,3}\d{1,3}\s?[A-Z]{3}", structured.value, re.IGNORECASE):
            return structured
        available_re = re.compile(
            r"\b((?:Mr|Mrs|Miss|Ms|Mx|Dr)\s+[A-Z][A-Za-z'’-]+(?:\s+[A-Z][A-Za-z'’-]+){0,4})\s+is\s+available\b"
        )
        for line in lines:
            match = available_re.search(line.text)
            if match:
                value = clean_val(match.group(1))
                return FieldExtraction(
                    value=value,
                    raw_value=value,
                    rule_id="fallback_claimant_available",
                    confidence=0.74,
                    source_span=SourceSpan(page_index=line.page_index, line_index=line.line_index, bbox=line.bbox),
                )
        return structured

    def _fallback_vehicle_model(self, lines: list[DocumentLine]) -> FieldExtraction:
        for line in lines:
            match = re.match(r"^\s*Vehicle\s*:\s*(.+?)\s*$", line.text, re.IGNORECASE)
            if not match:
                continue
            value = clean_val(match.group(1))
            if self._is_rejected_label_value(value, {"vehicle", "model", "make/model"}):
                continue
            if normalize_vrm(value) == value.replace(" ", "").upper() and re.fullmatch(r"[A-Z]{1,3}\d{1,3}[A-Z]{3}", normalize_vrm(value)):
                continue
            return FieldExtraction(
                value=value,
                raw_value=value,
                rule_id="fallback_vehicle_model_exact_vehicle",
                confidence=0.78,
                source_span=SourceSpan(page_index=line.page_index, line_index=line.line_index, bbox=line.bbox),
            )
        return self._extract_value_after_structured_label(
            lines,
            ("make/model", "make model", "our client's vehicle", "our clients vehicle", "client vehicle", "vehicle make", "vehicle model", "make"),
            "fallback_vehicle_model_structured",
            reject_labels={"model", "make", "vehicle", "vehicle model", "make/model"},
        )

    def _fallback_vrm(self, lines: list[DocumentLine], text: str) -> FieldExtraction:
        label_result = self._fallback_vrm_from_labels(lines)
        if label_result.value:
            return label_result
        context_words = ("reg", "registration", "vrm", "vehicle")
        for line in lines:
            lower = line.text.lower()
            if "located" in lower or "postcode" in lower or UK_POSTCODE_RE.search(line.text):
                continue
            if any(word in lower for word in context_words):
                match = VRM_RE.search(line.text)
                if match and not self._vrm_candidate_is_bad(match.group(1), line.text):
                    value = clean_val(match.group(1))
                    return FieldExtraction(
                        value=value,
                        raw_value=value,
                        rule_id="fallback_vrm_context",
                        confidence=0.78,
                        source_span=SourceSpan(page_index=line.page_index, line_index=line.line_index, bbox=line.bbox),
                    )
        match = VRM_RE.search(text)
        if match and not self._vrm_candidate_is_bad(match.group(1), text[max(0, match.start() - 20):match.end() + 20]):
            value = clean_val(match.group(1))
            return FieldExtraction(value=value, raw_value=value, rule_id="fallback_vrm_document", confidence=0.52)
        return FieldExtraction(value="", rule_id="fallback_vrm", confidence=0.0)

    def _fallback_vrm_from_labels(self, lines: list[DocumentLine]) -> FieldExtraction:
        labels = ("vehicle registration number", "vehicle registration", "registration", "vehicle reg", "client reg", "vrm", "reg")
        for label in labels:
            res = fuzzy_find_label(lines, label, threshold=0.72)
            if not res:
                continue
            idx, line, conf = res
            search_lines = [line] + lines[idx + 1:idx + 4]
            for candidate_line in search_lines:
                if self._is_label_only_value(candidate_line.text):
                    continue
                match = VRM_RE.search(candidate_line.text)
                if match and not self._vrm_candidate_is_bad(match.group(1), candidate_line.text):
                    value = clean_val(match.group(1))
                    return FieldExtraction(
                        value=value,
                        raw_value=value,
                        rule_id="fallback_vrm_label",
                        confidence=min(0.88, conf * 0.9),
                        source_span=SourceSpan(page_index=candidate_line.page_index, line_index=candidate_line.line_index, bbox=candidate_line.bbox),
                    )
        return FieldExtraction(value="", rule_id="fallback_vrm_label", confidence=0.0)

    def _vrm_candidate_is_bad(self, candidate: str, context: str) -> bool:
        compact = normalize_vrm(candidate)
        if len(compact) < 5 and not re.fullmatch(r"[A-Z]{1,3}\d{1,3}[A-Z]{1,3}", compact):
            return True
        if re.search(rf"\b{re.escape(candidate)}\s*\d[ABD-HJLNP-UW-Z]{{2}}\b", context, re.IGNORECASE):
            return True
        if compact in {"CLIENT", "VEHICLE", "REG", "MODEL"}:
            return True
        return False

    def _fallback_reference(self, lines: list[DocumentLine]) -> FieldExtraction:
        labels = ("reference", "ref", "claim no", "claim number", "case number", "our ref", "your ref")
        exact_label_re = re.compile(r"^\s*(?:our|your)?\s*ref(?:erence)?\s*:\s*(.+?)\s*$", re.IGNORECASE)
        subject_ref_re = re.compile(r"\bour\s+ref\s*:\s*([A-Z0-9./-]+(?:/[A-Z0-9.-]+)*)", re.IGNORECASE)
        slash_ref_re = re.compile(r"\b[A-Z]{1,4}(?:/[A-Z0-9.-]{1,8}){2,}\b", re.IGNORECASE)
        for line in lines[:10]:
            if not line.text.lower().startswith("subject:"):
                continue
            match = subject_ref_re.search(line.text) or slash_ref_re.search(line.text)
            if match:
                value = clean_val(match.group(1) if match.lastindex else match.group(0))
                return FieldExtraction(
                    value=value,
                    raw_value=value,
                    rule_id="fallback_reference_subject",
                    confidence=0.78,
                    source_span=SourceSpan(page_index=line.page_index, line_index=line.line_index, bbox=line.bbox),
                )
        label_only_ref_re = re.compile(r"^\s*(?:our|your)?\s*ref(?:erence)?\s*:\s*$", re.IGNORECASE)
        for idx, line in enumerate(lines[:30]):
            match = exact_label_re.match(line.text)
            if match:
                value = clean_val(match.group(1))
                if self._is_rejected_label_value(value, {"ref", "reference", "our ref", "your ref"}):
                    continue
                return FieldExtraction(
                    value=value,
                    raw_value=value,
                    rule_id="fallback_reference_exact_label",
                    confidence=0.84,
                    source_span=SourceSpan(page_index=line.page_index, line_index=line.line_index, bbox=line.bbox),
                )
            if label_only_ref_re.match(line.text):
                for next_line in lines[idx + 1:idx + 4]:
                    value = clean_val(next_line.text)
                    if not value or self._is_label_only_value(value) or value.lower().startswith("page "):
                        continue
                    if not (re.search(r"\d", value) and re.fullmatch(r"[A-Z0-9./ -]+", value, re.IGNORECASE)):
                        continue
                    return FieldExtraction(
                        value=value,
                        raw_value=value,
                        rule_id="fallback_reference_next_line",
                        confidence=0.76,
                        source_span=SourceSpan(page_index=next_line.page_index, line_index=next_line.line_index, bbox=next_line.bbox),
                    )
        by_label = self._fallback_label_value(lines, labels, FieldKey.REFERENCE)
        if by_label.value:
            return by_label
        ref_re = re.compile(r"\b(?:[A-Z]{2,6}[-/ ]?)?\d{4,}[A-Z0-9/-]*\b", re.IGNORECASE)
        for line in lines[:25]:
            if any(word in line.text.lower() for word in ("reference", "claim", "ref", "case")):
                match = ref_re.search(line.text)
                if match:
                    value = clean_val(match.group(0))
                    return FieldExtraction(
                        value=value,
                        raw_value=value,
                        rule_id="fallback_reference_pattern",
                        confidence=0.65,
                        source_span=SourceSpan(page_index=line.page_index, line_index=line.line_index, bbox=line.bbox),
                    )
        return FieldExtraction(value="", rule_id="fallback_reference", confidence=0.0)

    def _fallback_context_date(self, lines: list[DocumentLine], context_words: tuple[str, ...], field_key: FieldKey) -> FieldExtraction:
        for idx, line in enumerate(lines):
            lower = line.text.lower()
            if not any(word in lower for word in context_words):
                continue
            search_lines = [line] + lines[idx + 1:idx + 3]
            for candidate_line in search_lines:
                match = DATE_RE.search(candidate_line.text)
                if match:
                    value = clean_val(match.group(0))
                    return FieldExtraction(
                        value=value,
                        raw_value=value,
                        rule_id=f"fallback_{field_key.value}_context",
                        confidence=0.7,
                        source_span=SourceSpan(
                            page_index=candidate_line.page_index,
                            line_index=candidate_line.line_index,
                            bbox=candidate_line.bbox,
                        ),
                    )
        for line in lines[:12]:
            match = DATE_RE.search(line.text)
            if match:
                value = clean_val(match.group(0))
                return FieldExtraction(
                    value=value,
                    raw_value=value,
                    rule_id=f"fallback_{field_key.value}_top_date",
                    confidence=0.5,
                    source_span=SourceSpan(page_index=line.page_index, line_index=line.line_index, bbox=line.bbox),
                )
        return FieldExtraction(value="", rule_id=f"fallback_{field_key.value}", confidence=0.0)

    def _fallback_address(self, lines: list[DocumentLine]) -> FieldExtraction:
        labels = ("inspection address", "address", "location", "repairer", "garage", "bodyshop")
        for label in labels:
            res = fuzzy_find_label(lines, label, threshold=0.72)
            if not res:
                continue
            idx, line, conf = res
            if self._address_contains_narrative(line.text):
                continue
            collected: list[str] = []
            same = self._extract_label_same_line(lines, {"labels": [label]}, "fallback_inspection_address")
            if same.value:
                collected.append(same.value)
            if same.value and UK_POSTCODE_RE.search(same.value):
                value = clean_val("\n".join(collected))
                if value and not self._address_contains_narrative(value):
                    return FieldExtraction(
                        value=value,
                        raw_value=value,
                        rule_id="fallback_inspection_address",
                        confidence=min(0.82, conf * 0.8),
                        source_span=SourceSpan(page_index=line.page_index, line_index=line.line_index, bbox=line.bbox),
                    )
            for next_line in lines[idx + 1:idx + 8]:
                value = clean_val(next_line.text)
                if not value:
                    if collected:
                        break
                    continue
                value_lower = value.lower()
                if (
                    DATE_RE.search(value)
                    or value_lower in {"tel", "telephone", "email"}
                    or value_lower.startswith(("tel:", "tele:", "telephone:", "mobile", "email:", "vehicle:", "reg:"))
                ):
                    break
                collected.append(value)
                if UK_POSTCODE_RE.search(value):
                    break
            value = clean_val("\n".join(collected))
            if value and not self._address_contains_narrative(value) and (UK_POSTCODE_RE.search(value) or len(collected) >= 2):
                return FieldExtraction(
                    value=value,
                    raw_value=value,
                    rule_id="fallback_inspection_address",
                    confidence=min(0.82, conf * 0.8),
                    source_span=SourceSpan(page_index=line.page_index, line_index=line.line_index, bbox=line.bbox),
                )
        for idx, line in enumerate(lines):
            if UK_POSTCODE_RE.search(line.text):
                collected: list[str] = []
                for prev in reversed(lines[max(0, idx - 5):idx]):
                    prev_value = clean_val(prev.text)
                    if not prev_value:
                        continue
                    prev_lower = prev_value.lower()
                    if any(
                        phrase in prev_lower
                        for phrase in (
                            "available at",
                            "introducer",
                            "please make arrangements",
                            "please arrange",
                            "provide a report",
                            "i have advised",
                        )
                    ):
                        if collected:
                            break
                        continue
                    if len(prev_value.split()) > 9:
                        if collected:
                            break
                        continue
                    collected.insert(0, prev_value)
                    if len(collected) >= 3:
                        break
                collected.append(clean_val(line.text))
                value = clean_val("\n".join(collected))
                return FieldExtraction(
                    value=value,
                    raw_value=value,
                    rule_id="fallback_address_postcode_block",
                    confidence=0.6,
                    source_span=SourceSpan(page_index=line.page_index, line_index=line.line_index, bbox=line.bbox),
                )
        return FieldExtraction(value="", rule_id="fallback_inspection_address", confidence=0.0)
