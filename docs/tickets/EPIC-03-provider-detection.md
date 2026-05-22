# EPIC-03 Provider Detection

## Objective

Replace simple phrase matching with explainable provider detection.

## Deliverables

- Required, optional, and negative phrase matching.
- Confidence score and tie-break rules.
- Detection diagnostics for UI.
- Tests for ambiguous providers such as FW and MP variants.

## Acceptance Criteria

- Providers requiring multiple phrases match only when all required phrases exist.
- Negative phrase matches reject a provider.
- Diagnostics list matched and missing terms.
- Unknown documents remain unmapped without producing JSON.

