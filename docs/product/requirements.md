# Product Requirements

## Problem

Collision Engineers receives instruction documents from many work providers. Those documents arrive as PDF, DOCX, DOC, MSG, and EML files with inconsistent layouts. Staff need the key values in an EVA-compatible JSON format.

## Users

- Admin users importing new instructions.
- Power users maintaining provider presets and extraction rules.
- Developers extending readers and rule behavior.

## Success Criteria

- A user can drag in one or more instruction documents.
- The app detects the provider with visible confidence and diagnostics.
- The app extracts the fixed field set into editable values.
- Required fields are validated before JSON export.
- Exported JSON matches the EVA contract.
- A regression suite catches parser changes that affect known documents.

## Required Fields

The required export fields are:

- Work Provider
- VRM
- Vehicle Model
- Claimant Name
- Reference
- Incident Date
- Instruction Date

Optional but supported:

- Inspection Date
- Inspection Address
- Accident Circumstances
- VAT Status
- Mileage
- Mileage Unit

## Non-Goals for v2 Foundation

- Fully automatic parsing with no review.
- Direct EVA API submission in the first implementation milestone.
- Replacing human judgment for inspection address interpretation.
- Training a custom ML model before the deterministic parser is covered by tests.

