from __future__ import annotations

import re
from typing import Any
from cedocumentmapper_v2.domain.models import DocumentModel, ProviderMatch


def normalize_search_text(value: str) -> str:
    """Normalize text for robust matching, matching v1 behavior."""
    value = value.lower().replace("\r", "\n").replace("\t", " ")
    value = re.sub(r"[^\w\n ]+", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


class ProviderDetector:
    def detect(self, document: DocumentModel, providers: list[dict[str, Any]]) -> ProviderMatch:
        """Pick the best matching provider config from the list of providers."""
        plain_text = document.plain_text
        lower_text = plain_text.lower()
        normalized_text = normalize_search_text(plain_text)

        best_match: ProviderMatch | None = None
        best_priority = -1
        best_required_count = -1

        for provider in providers:
            if not provider.get("enabled", True):
                continue

            provider_id = provider.get("id")
            name = provider.get("name", "Unknown")
            detect_cfg = provider.get("detect", {})
            required_phrases = detect_cfg.get("required_phrases", [])
            optional_phrases = detect_cfg.get("optional_phrases", [])
            negative_phrases = detect_cfg.get("negative_phrases", [])
            min_confidence = detect_cfg.get("minimum_confidence", 0.75)
            priority = provider.get("priority", 0)

            # Check phrases
            matched_req = []
            missing_req = []
            for phrase in required_phrases:
                if self._phrase_in_text(phrase, lower_text, normalized_text):
                    matched_req.append(phrase)
                else:
                    missing_req.append(phrase)

            # If any required phrase is missing, confidence is 0
            if missing_req:
                continue

            # Check negative phrases
            matched_neg = []
            for phrase in negative_phrases:
                if self._phrase_in_text(phrase, lower_text, normalized_text):
                    matched_neg.append(phrase)

            # If any negative phrase matched, this provider is rejected
            if matched_neg:
                continue

            # Check optional phrases
            matched_opt = []
            for phrase in optional_phrases:
                if self._phrase_in_text(phrase, lower_text, normalized_text):
                    matched_opt.append(phrase)

            # Compute confidence
            # Base confidence of 0.8 if all required match
            # Remaining 0.2 scaled by matched optional phrases
            if optional_phrases:
                opt_ratio = len(matched_opt) / len(optional_phrases)
                confidence = 0.8 + 0.2 * opt_ratio
            else:
                confidence = 1.0

            if confidence < min_confidence:
                continue

            # Tie-break logic:
            # 1. Higher confidence wins
            # 2. Higher priority wins
            # 3. More required phrases (more specific fingerprint) wins
            is_better = False
            if best_match is None:
                is_better = True
            else:
                if confidence > best_match.confidence:
                    is_better = True
                elif confidence == best_match.confidence:
                    if priority > best_priority:
                        is_better = True
                    elif priority == best_priority:
                        if len(required_phrases) > best_required_count:
                            is_better = True

            if is_better:
                best_match = ProviderMatch(
                    provider_id=provider_id,
                    provider_name=name,
                    confidence=confidence,
                    matched_terms=tuple(matched_req + matched_opt),
                    missing_terms=tuple(missing_req),
                    rejected_terms=tuple(matched_neg),
                )
                best_priority = priority
                best_required_count = len(required_phrases)

        if best_match is not None:
            return best_match

        return ProviderMatch(
            provider_id=None,
            provider_name="Unknown / Unmapped",
            confidence=0.0,
        )

    def _phrase_in_text(self, phrase: str, lower_text: str, normalized_text: str) -> bool:
        raw_phrase = phrase.lower().strip()
        norm_phrase = normalize_search_text(phrase)
        if raw_phrase and raw_phrase in lower_text:
            return True
        if norm_phrase and norm_phrase in normalized_text:
            return True
        return False
