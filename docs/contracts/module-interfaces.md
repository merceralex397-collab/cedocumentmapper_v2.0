# Module Interface Contracts

## DocumentReader

```python
class DocumentReader(Protocol):
    supported_extensions: frozenset[str]
    def read(self, path: Path) -> DocumentModel: ...
```

Reader failures should raise typed exceptions. Recoverable reader issues should be returned in `DocumentModel.reader_notes`.

## ProviderDetector

```python
class ProviderDetector(Protocol):
    def detect(self, document: DocumentModel, providers: ProviderCatalog) -> ProviderMatch: ...
```

Provider detection must explain:

- matched required phrases
- missing required phrases
- matched optional phrases
- rejected negative phrases
- final confidence

## RuleEngine

```python
class RuleEngine(Protocol):
    def extract_record(self, document: DocumentModel, provider: ProviderConfig) -> ExtractedRecord: ...
```

The rule engine applies configured field rules and then field normalizers. It should not perform UI fallback prompts.

## Exporter

```python
class Exporter(Protocol):
    def export(self, record: ExtractedRecord) -> str | bytes: ...
```

The EVA JSON exporter returns a JSON string and leaves file placement to the application service.

