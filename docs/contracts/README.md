# Contract Overview

Contracts define stable boundaries before implementation.

Files:

- `document-model.md`: canonical document shape.
- `module-interfaces.md`: reader, detector, rule, normalizer, exporter contracts.
- `eva-json.schema.json`: required final JSON shape.
- `provider-config.schema.json`: provider preset format.
- `extraction-rule.schema.json`: rule config format.
- `expected-fixture.schema.json`: regression fixture format.

Any implementation change that changes data shape must update these contracts and the matching ticket.

