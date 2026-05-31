import json
from pathlib import Path

from cedocumentmapper_v2.cli import main


def test_cli_providers_list(tmp_path, capsys):
    app_data = tmp_path / "appdata"
    app_data.mkdir()
    (app_data / "providers.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "providers": [
                    {
                        "id": "test",
                        "name": "Test Provider",
                        "work_provider": "TEST",
                        "enabled": True,
                        "priority": 1,
                        "detect": {"required_phrases": ["Test Provider"]},
                        "field_rules": {},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    code = main(["--app-data-dir", str(app_data), "providers", "list"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["id"] == "test"


def test_cli_detect_eml(tmp_path, capsys):
    app_data = tmp_path / "appdata"
    app_data.mkdir()
    (app_data / "providers.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "providers": [
                    {
                        "id": "test",
                        "name": "Test Provider",
                        "work_provider": "TEST",
                        "enabled": True,
                        "priority": 1,
                        "detect": {"required_phrases": ["Unique Test Phrase"]},
                        "field_rules": {},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    email_path = tmp_path / "instruction.eml"
    email_path.write_text(
        "Subject: Unique Test Phrase\nFrom: sender@example.com\nTo: receiver@example.com\nDate: Sun, 31 May 2026 10:00:00 +0000\n\nBody",
        encoding="utf-8",
    )

    code = main(["--app-data-dir", str(app_data), "detect", str(email_path)])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["provider_id"] == "test"
