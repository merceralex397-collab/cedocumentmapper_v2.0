# Plan to Fully Exceed `cedocumentmapper`

## Purpose

This is a reinvention plan, not a parity patch.

The goal is to build a v2 extraction system that fully exceeds the original `cedocumentmapper` on:

- document understanding
- extraction accuracy
- explainability
- maintainability
- regression safety
- provider onboarding
- batch throughput
- operator review speed

The original app is the benchmark, not the design target. v2 should use the original output as one comparison signal, then move beyond it with a richer document model, candidate extraction, confidence scoring, validation, and feedback-driven provider profiles.

The CLI plan in `docs/plans/cliplan.md` is a required enabler because it gives v2 a repeatable headless way to process documents, export structured results, and compare extraction outcomes. The original `cedocumentmapper` must not receive a CLI implementation; comparisons against it should be done through read-only scripts that import or invoke its existing code.

## Current Baseline

Findings from `docs/plans/comparisonreport.md`:

- v2 reads the same broad document formats, but does not reproduce v1 extraction behavior.
- Provider detection matched v1 on the comparable corpus.
- Field extraction does not match v1: 82 of 91 comparable non-DOC files had at least one difference.
- v1 extracted many nonblank values that v2 blanked:
  - `vrm`: 33
  - `incident_date`: 29
  - `claimant_name`: 24
  - `reference`: 24
  - `vehicle_model`: 23
  - `inspection_address`: 18
  - `inspection_date`: 12
  - `instruction_date`: 10
  - `vat_status`: 10

The immediate technical causes are known:

- v1 `single_label` implicitly supports same-line and next-line values; v2 migration maps it to same-line only.
- v1 fixed-position rules operate over raw `splitlines()` text, including blank lines; v2 line models usually omit blanks.
- v1 presence checks support negative values such as VAT `No` and mileage unit `Km`; v2 presence checks return positive value or blank.
- v1 has fallback extractors for references, VRMs, names, models, addresses, and dates.
- v2 currently preserves less of the blank/block separation that some v1 rules depended on.

These are parity problems, but solving only these would still leave v2 as a cleaned-up copy of v1. The target is a stronger interpretation engine.

## Product Goal

For every supported document, v2 should produce:

- the best extracted value for each target field
- raw value and normalized value
- evidence spans tied to document lines, pages, OCR confidence, and layout blocks
- alternative candidates when confidence is not decisive
- a reasoned confidence score
- validation issues that explain what looks missing, inconsistent, or suspicious
- a review UI and CLI output that make correction fast
- enough persisted evidence to improve rules without re-reading the source document

Success is not "match v1." Success is:

- v2 equals or beats v1 on every known fixture.
- v2 identifies and explains when v1 was wrong.
- v2 extracts useful candidates from documents v1 cannot handle confidently.
- v2 can be improved through fixtures, provider profiles, and review feedback without changing core code for every provider.

## Core Design Principles

1. Preserve evidence before extracting.
   - Readers should capture all useful text, layout, block, table, OCR, metadata, and attachment facts.
   - Extraction should consume evidence, not raw file APIs.

2. Extract candidates, then decide.
   - Do not let one brittle rule decide a field too early.
   - Multiple strategies should propose candidates.
   - A resolver ranks candidates using labels, layout, provider profile, field validators, and cross-field consistency.

3. Make every value explainable.
   - Every extracted field should point back to evidence.
   - The UI and CLI should show why a value won, what alternatives existed, and which checks passed or failed.

4. Separate provider knowledge from engine logic.
   - Provider profiles should describe detection, expected layouts, labels, negative indicators, date conventions, and workflow type.
   - The engine should supply reusable extraction strategies.

5. Treat v1 as a comparator, not an oracle.
   - v1 output should be captured in regression reports.
   - Human-approved expected fixtures are the source of truth.

6. Optimize for batch work.
   - The app should process many documents safely, cache expensive reads, avoid repeated OCR, and produce batch diagnostics.

## Target Architecture

```text
Source file
  -> Reader pipeline
  -> Rich DocumentModel
  -> Provider detection
  -> Evidence index
  -> Candidate extractors
  -> Candidate resolver
  -> Normalizers
  -> Cross-field validators
  -> Review package
  -> UI / CLI / exporters
  -> Feedback and regression artifacts
```

### New Subsystems

1. `application`
   - Shared workflow service for CLI and UI.
   - Owns process orchestration, provider catalog access, batch runs, engineer overlays, exports, and report generation.

2. `evidence`
   - Builds searchable indexes over `DocumentModel`.
   - Exposes line, block, page, table, key-value, and OCR evidence.

3. `candidates`
   - Field-specific and generic extractors propose candidates.
   - Each candidate has value, field, source evidence, strategy, raw score, and rationale.

4. `resolution`
   - Chooses the best candidate per field.
   - Keeps alternates.
   - Applies provider preferences, validators, cross-field consistency, and operator overrides.

5. `learning`
   - Records corrections and fixture outcomes.
   - Proposes provider rule improvements.
   - Does not silently auto-change provider behavior without review.

6. `reports`
   - Produces comparison reports against expected fixtures and v1 outputs.
   - Produces provider health dashboards.

## Rich Document Model Upgrade

Extend the canonical `DocumentModel` without breaking current readers.

Add optional evidence concepts:

- `blocks`: layout groups with bbox, page, text, block type, and reading order.
- `tables`: detected table structures with rows, cells, bbox, and source engine.
- `kv_pairs`: candidate key-value pairs found by readers or evidence indexing.
- `images`: embedded image metadata, page association, dimensions, hash, and extractable bytes reference.
- `attachments`: email attachment metadata and optional linked document models.
- `ocr_layers`: OCR output by page, confidence, engine, DPI, and trigger reason.
- `warnings`: structured reader warnings, not just strings.
- `fingerprint`: stable hash of source bytes and reader settings for cache keys.

Preserve both:

- raw text stream including blank lines and block separators
- normalized line stream suitable for extraction

This prevents the fixed-line and blank-line regressions while still supporting structured extraction.

## Reader Strategy

### PDF

Implement a multi-pass PDF reader:

- PyMuPDF text blocks with coordinates.
- PyMuPDF dict lines and spans for exact line evidence.
- pypdf fallback for broken text layers and `/uniXXXX` decoding.
- Table detection where available.
- OCR only when warranted by a clear decision policy.
- Embedded image inventory without forcing extraction.

The PDF reader should classify pages:

- selectable text page
- scanned letter page
- photo/image bundle page
- hybrid page
- form/table page
- low-confidence OCR page

OCR policy should be explicit:

- OCR 1-2 page scanned letters automatically.
- Do not OCR likely photo bundles by default.
- Allow CLI/UI override for forced OCR.
- Cache OCR by file hash, page hash, DPI, and OCR settings.
- Return "OCR skipped" reasons in diagnostics.

### DOCX

Read:

- body paragraphs
- tables
- headers and footers
- text boxes
- document properties
- embedded images
- comments if present
- hyperlinks and field codes where useful

Preserve paragraph order and table cell relationships rather than flattening too early.

### DOC

Fully exceed v1 by supporting:

- Word COM when available.
- LibreOffice conversion.
- antiword fallback.
- clear dependency diagnostics.
- optional conversion cache.

DOC extraction should capture whether headers, footers, tables, and text boxes survived the chosen path.

### MSG / EML

Improve email handling:

- Normalize headers into structured metadata.
- Preserve body alternatives: plain, HTML-stripped, RTF-stripped.
- Extract attachment names and optional attachment document models.
- Support date extraction from structured headers before text rules.
- Identify forwarded-message boundaries and original sender/date blocks.

## Evidence Index

Build an index once per document:

- normalized searchable text
- exact raw lines
- nonblank line sequence
- blank-preserving line sequence
- label index by normalized token
- key-value candidates from punctuation, table cells, and adjacent lines
- date candidates
- VRM candidates
- reference candidates
- person/name candidates
- postcode/address candidates
- vehicle model candidates
- monetary and mileage candidates

The index should support queries like:

- label exact match
- label fuzzy match
- label near value
- same line value
- next nonblank line value
- value above/below label
- value in table cell to right of label
- value in same block as label
- value between anchors
- first plausible date near provider letterhead
- first plausible VRM near vehicle words

## Candidate Extraction

Every field should receive candidates from multiple strategies.

### Generic Strategies

- same-line label
- next-line label
- same-or-next label
- line offset
- fixed line and fixed line range
- between labels
- regex
- table key-value
- block key-value
- presence positive/negative
- email header field
- document metadata field
- provider-specific manual value
- OCR-tolerant fuzzy label

### Field-Specific Strategies

#### Work Provider

- provider profile manual value
- detected provider default value
- fallback to provider name only when explicitly allowed

#### VRM

- label-based candidates near registration labels
- UK VRM regex over full document
- table cell candidates near vehicle labels
- candidate normalization with space removal and uppercase
- reject candidates that are too long, date-like, reference-like, or common words
- boost candidates near vehicle/model labels

#### Vehicle Model

- label-based value
- table cell value near make/model labels
- value near VRM in vehicle details block
- remove VRM and registration prefixes from model candidate
- keep make/model phrase when available, not only one token

#### Claimant Name

- label-based value near client/claimant/policyholder labels
- title-name patterns
- email/client metadata if provider supports it
- reject values equal to labels such as `Name`
- reject company/legal boilerplate unless provider expects company claimants

#### Reference

- label-based value
- provider-specific reference pattern library
- prominent top-of-document reference candidates
- email subject reference extraction
- reject dates, VRMs, phone numbers, and generic labels

#### Incident Date

- label-based values
- dates near accident/incident/RTA/collision labels
- dates in structured tables
- date normalization with ordinal, ISO, month-name, short-year, and compact variants
- reject instruction dates when label context says sent/date instructed/report due

#### Instruction Date

- email header date when source is email
- letterhead/top-of-document date
- date near instructed/instruction/received labels
- fixed line fallback only after context validation
- provider-specific preference order

#### Inspection Date

- report due date
- inspection booked/date arranged/date instructed context
- current date manual provider option
- reject instruction date unless provider explicitly maps it

#### Inspection Address

- multi-line label extraction
- postcode-based block extraction
- address-line classifier
- garage/bodyshop/location special values
- image-based assessment manual value
- six-line canonical export form
- preserve raw address and normalized address separately

#### Accident Circumstances

- between-label extraction
- paragraph section extraction
- stop at known next headings
- preserve paragraph breaks where meaningful
- strip obvious unrelated sections only when evidence is strong

#### VAT Status

- positive/negative presence strategy
- explicit labeled value
- phrase interpretation:
  - VAT registered -> Yes
  - not VAT registered -> No
  - VAT Status: No -> No
- avoid positive match when preceded by negation

#### Mileage

- label-based speedo/odometer/mileage values
- numeric candidate parsing
- reject phone numbers, dates, costs, and references
- normalize to digits

#### Mileage Unit

- explicit unit near mileage
- positive/negative presence:
  - miles/mi -> Miles
  - km/kilometres/kilometers -> Km
- provider default if configured
- blank only when unknown

## Candidate Resolver

The resolver should rank candidates using:

- extractor strategy reliability
- provider profile priority
- label similarity
- source proximity
- layout relationship
- field-specific validity
- cross-field consistency
- OCR confidence
- historical fixture performance
- operator override history

Each winning field should include:

- selected value
- raw value
- normalized value
- confidence
- strategy
- evidence span
- explanation
- alternatives
- validation issues

Confidence bands:

- `0.90-1.00`: high confidence, no review emphasis
- `0.70-0.89`: likely, show mild review cue
- `0.40-0.69`: uncertain, require review
- `<0.40`: treat as missing unless user accepts

## Provider Profiles

Replace brittle provider configs with structured profiles.

Profile sections:

- identity:
  - id
  - display name
  - work provider export value
  - enabled flag
  - priority
- detection:
  - required phrases
  - optional phrases
  - negative phrases
  - subject/email hints
  - attachment hints
- document types:
  - instruction
  - engineer report
  - image bundle
  - mixed email
- field strategy preferences:
  - enabled strategies per field
  - label aliases
  - table/header preferences
  - fixed-line fallback only where unavoidable
- normalization options:
  - address postcode enforcement
  - current-date inspection date
  - provider default mileage unit
- validation expectations:
  - expected reference pattern
  - likely date ordering
  - allowed blank optional fields
- UI hints:
  - fields requiring review
  - provider-specific help text

Keep unknown provider fields during migration.

## Human Review Redesign

The UI should become an evidence review workstation, not just a form.

For each field:

- show selected value
- show confidence
- show source page/line
- highlight source span in preview
- show alternatives
- allow one-click alternative selection
- allow manual edit
- show validation warnings
- show "why this value" explanation

For provider/rule maintenance:

- show missed expected fields from regression corpus
- show common labels found in documents
- allow creating a rule from highlighted text
- allow testing a rule across all fixtures for that provider
- show before/after extraction diff before saving rule changes

## CLI and Comparison Harness

Use `docs/plans/cliplan.md` to build a CLI capable of:

- reading documents
- extracting records
- exporting structured JSON
- running provider-specific batches
- running rule sandboxes
- producing comparison reports

Add a comparison harness that:

- runs v2 through the CLI or shared service
- runs v1 by importing its existing code in read-only mode
- never modifies or adds CLI functionality to v1
- compares both outputs against approved fixtures
- classifies differences:
  - v2 correct, v1 wrong
  - v1 correct, v2 wrong
  - both wrong
  - both acceptable but different normalization
  - fixture needs human decision

The harness should produce:

- per-provider scorecards
- per-field scorecards
- regression diffs
- confidence calibration reports
- examples requiring fixture approval

## Regression Corpus Strategy

Current fixture coverage is far too small for the observed corpus.

Build fixture coverage in layers:

1. Smoke fixtures
   - one document per supported file type
   - one document per reader path

2. Provider fixtures
   - at least one approved fixture per provider
   - prioritize providers where v1 currently beats v2

3. Variation fixtures
   - same provider across PDF, DOCX, DOC, MSG where present
   - scanned letter PDFs
   - photo bundle PDFs
   - emails with HTML-only body
   - documents with table layouts
   - documents with split label/value lines

4. Negative fixtures
   - image-only document with no instruction data
   - wrong provider phrases
   - ambiguous provider phrases
   - missing required fields
   - misleading VAT phrases

5. Gold fixtures
   - human-approved expected values
   - raw evidence references
   - allowed alternatives where business-valid

Every real parser fix must add or update a fixture.

## Evaluation Metrics

Track objective extraction quality:

- exact match by field
- normalized match by field
- required-field completion rate
- false positive rate
- false blank rate
- provider detection accuracy
- confidence calibration
- average review touches per document
- batch success rate
- OCR time per document
- import/export wall-clock time
- memory use on large PDFs

Minimum target before replacing v1 operationally:

- 100 percent provider detection on approved corpus
- 100 percent required-field extraction or justified review-required flag
- 0 known v1-wins/v2-blanks on approved corpus
- lower false-positive rate than v1
- all exports match schema
- batch processing does not freeze UI

## Performance and Reliability

Performance improvements should be designed into the architecture:

- cache document reads by file hash
- cache OCR by page image hash
- avoid sending full PDFs as base64 unless needed
- serve previews through local file tokens
- stream batch progress
- run expensive OCR/extraction off the UI thread
- expose cancellation for batch/OCR jobs
- cap OCR by policy, but allow explicit override
- reuse evidence indexes during rule sandbox runs

Reliability:

- no silent fallback that hides data loss
- every fallback records a diagnostic
- every export records source document fingerprint and provider version
- every migration preserves unknown fields
- rule changes can be tested before saving

## Migration Strategy

Do not treat v1 provider files as the future profile format.

Migration stages:

1. Import v1 provider config losslessly into a compatibility profile.
2. Preserve original rule data in metadata.
3. Generate v2 candidate-strategy defaults.
4. Run provider fixtures and compare to v1.
5. Promote stable providers from compatibility profile to native profile.
6. Keep a rollback path to the prior provider profile version.

Provider migration should explicitly handle:

- `single_label` -> same-or-next label strategy
- fixed-position ranges
- positive/negative presence rules
- manual values
- current-date fields
- engineer-report provider flags
- address postcode enforcement
- legacy fallback methods as candidate strategies, not hidden hard-coded branches

## Implementation Roadmap

### Phase 1: Measurement and CLI Foundation

- Implement the CLI and shared application service from `cliplan.md`.
- Add batch extraction command with JSON output.
- Add read-only v1 comparator harness.
- Generate baseline scorecards for all documents in `docs/Instructions`.
- Add initial approved fixtures for the highest-difference providers:
  - ALISON PDFs
  - BLACK PDFs
  - DFD PDFs
  - FW MSG
  - HDUK PDFs
  - QDOS PDFs
  - SBL PDFs

Exit criteria:

- v2 CLI can process the corpus headlessly.
- v1-v2 comparison report is reproducible by command.
- Fixture failures are visible and grouped by field/provider.

### Phase 2: Rule Parity Without Copying v1

- Add same-or-next label strategy.
- Add fixed-line range support.
- Add positive/negative presence support.
- Add raw blank-preserving line stream.
- Add antiword DOC fallback.
- Update migration to preserve these semantics.
- Add tests proving v1-wins/v2-blanks are eliminated where fixtures approve v1 values.

Exit criteria:

- No known parity loss from the comparison report remains unexplained.
- v2 can intentionally differ from v1 only when fixture approval says v2 is better.

### Phase 3: Evidence Index and Candidate Engine

- Build evidence indexing.
- Implement candidate extraction framework.
- Add field-specific candidate strategies.
- Add candidate resolver with explanations and alternatives.
- Return alternatives in CLI JSON and UI bridge output.

Exit criteria:

- Each field has at least two independent candidate strategies where meaningful.
- Extracted values include explanation and evidence.
- Low-confidence fields are visibly review-required.

### Phase 4: Reader Upgrade

- Add rich PDF page classification.
- Add table extraction.
- Add OCR cache and explicit OCR diagnostics.
- Improve DOCX table/textbox/header/footer representation.
- Improve MSG/EML structured metadata and forwarded-message handling.
- Add DOC conversion/cache diagnostics.

Exit criteria:

- Readers preserve richer evidence than v1.
- Rule extraction no longer depends on fragile flattened text alone.
- Large scanned/photo documents do not freeze the UI.

### Phase 5: Review UI Reinvention

- Add evidence-backed field review.
- Show source highlights and alternatives.
- Add provider health and rule testing views.
- Add rule creation from highlighted evidence.
- Add batch review queue.

Exit criteria:

- Users can resolve uncertain fields faster than in v1.
- Power users can test provider changes against fixtures before saving.

### Phase 6: Continuous Improvement

- Record correction events.
- Generate suggested provider-rule updates.
- Add confidence calibration reports.
- Add provider scorecards to the app.
- Build release gates around fixture and corpus metrics.

Exit criteria:

- Every parser/rule change produces measurable quality impact.
- Provider onboarding is driven by evidence and tests, not code edits.

## Contract Changes Needed

Planned contract additions:

- `DocumentModel.blocks`
- `DocumentModel.tables`
- `DocumentModel.images`
- `DocumentModel.attachments`
- `DocumentModel.ocr_layers`
- `DocumentModel.fingerprint`
- `DocumentLine.raw_text`
- `DocumentLine.is_blank`
- `FieldCandidate`
- `FieldDecision`
- `ExtractionReport`
- rule `absent_value`
- rule `line_end`
- rule `fallback_next_line` or new `label_same_or_next_line`
- provider profile versioning metadata

All contract changes must update:

- markdown contract docs
- JSON schemas
- migration tests
- fixture schema where necessary

## Testing Plan

Add tests in these categories:

- reader evidence tests
- rule strategy unit tests
- candidate extractor tests
- resolver ranking tests
- field normalization tests
- cross-field validation tests
- provider migration tests
- CLI golden-output tests
- UI bridge service parity tests
- corpus regression tests
- v1 comparator tests
- performance smoke tests for large PDFs and OCR skip behavior

Important test cases from the comparison:

- ALISON PDF incident date and address.
- BLACK PDF VRM/reference/address.
- DFD PDF required fields.
- FW MSG claimant should not become literal `Name`.
- AX instruction date should not become `Engineer Instructions`.
- SBL VAT `No` should not become blank.
- CNX/EVA engineer reports with blank work provider should be handled deliberately.
- image-only documents should be classified and not falsely extracted.

## Operational Rollout

Rollout should be controlled by provider and corpus metrics:

1. Internal CLI-only benchmark.
2. Read-only UI preview mode showing v1/v2/new-engine differences.
3. Provider-by-provider enablement.
4. Batch mode for low-risk providers first.
5. Full replacement only after scorecards beat v1.

Do not remove compatibility behavior until:

- fixtures cover every active provider
- current user provider configs migrate cleanly
- export outputs have been validated against EVA expectations
- users have a way to inspect uncertain decisions

## Definition of "Fully Exceeds v1"

v2 fully exceeds `cedocumentmapper` when:

- It can process every file type v1 can process.
- It can extract every field v1 can extract on the approved corpus.
- It can correctly extract fields v1 misses or mis-extracts.
- It explains every extracted value with source evidence.
- It reports alternatives and uncertainty instead of silently blanking or guessing.
- It supports batch processing and engineer-report overlay at least as well as v1.
- It avoids UI freezes from OCR, large PDFs, or batch operations.
- It lets power users improve provider behavior through evidence-backed tools.
- It has repeatable CLI and test harnesses for every workflow.
- It makes fixture-backed quality measurement a normal development step.

## Immediate Next Actions

1. Implement `cliplan.md` enough to run `read`, `detect`, `extract`, and `process` headlessly.
2. Build the v1 comparator harness without changing v1.
3. Convert the comparison-report examples into approved fixtures.
4. Add same-or-next label, fixed-line range, and negative presence behavior.
5. Add the first evidence-index prototype for labels, dates, VRMs, references, and postcodes.
6. Generate provider scorecards and use them to prioritize the next extraction strategies.

