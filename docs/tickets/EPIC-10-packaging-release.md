# EPIC-10 Packaging and Release

## Objective

Package v2 as a portable Windows executable.

## Deliverables

- PyInstaller spec.
- Bundled providers seed.
- Bundled Tesseract.
- Release checklist automation where practical.
- Versioned release notes template.

## Acceptance Criteria

- Clean Windows machine can run the executable.
- OneDrive Desktop/Documents paths resolve correctly.
- Existing user providers are not overwritten.
- `providers.json` seed is included in packaged first-run behavior.

