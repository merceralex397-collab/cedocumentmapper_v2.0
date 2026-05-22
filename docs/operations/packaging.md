# Packaging and Release

## Target

A portable Windows executable remains the target delivery format.

## Required Bundled Assets

- application icon
- bundled `providers.json` seed
- bundled Tesseract binary and `tessdata/eng.traineddata`

## Packaging Requirements

- The executable must resolve Documents and Desktop through the Windows Shell API so OneDrive redirected folders work.
- First run must seed provider config into the user's real Documents folder.
- Existing user config must not be overwritten by bundled defaults.
- Releases must include `requirements.txt`, release notes, and the executable.

## Release Checklist

- All tests pass.
- Fixture diff report reviewed.
- Provider schema migration tested against current v1 config.
- Clean machine first-run test completed.
- OneDrive Documents/Desktop path test completed.
- Scanned PDF OCR smoke test completed.
- MSG import smoke test completed.

