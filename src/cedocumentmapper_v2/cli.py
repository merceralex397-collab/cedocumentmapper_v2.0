from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path
from typing import Any

from cedocumentmapper_v2.application import DocumentMapperService
from cedocumentmapper_v2.domain.models import FieldKey
from cedocumentmapper_v2.rules import RuleEngine

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".eml", ".msg"}


def _print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def _service(args: argparse.Namespace) -> DocumentMapperService:
    return DocumentMapperService(app_data_dir=Path(args.app_data_dir) if getattr(args, "app_data_dir", None) else None)


def _expand_paths(paths: list[str], recursive: bool = False) -> list[Path]:
    expanded: list[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            iterator = path.rglob("*") if recursive else path.glob("*")
            expanded.extend(sorted(p for p in iterator if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS))
        else:
            expanded.append(path)
    return expanded


def _source_stem(path: Path) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in path.stem) or "document"


def cmd_gui(args: argparse.Namespace) -> int:
    from cedocumentmapper_v2.ui import start_webview

    start_webview(debug=args.dev or args.debug)
    return 0


def cmd_read(args: argparse.Namespace) -> int:
    service = _service(args)
    document = service.read_document(args.path)
    if args.json:
        _print_json(service.document_to_dict(document))
    elif args.plain_text:
        print(document.plain_text)
    else:
        lines = sum(len(page.lines) for page in document.pages)
        _print_json(
            {
                "source_path": str(document.source_path),
                "source_type": document.source_type,
                "pages": len(document.pages),
                "lines": lines,
                "reader_notes": list(document.reader_notes),
            }
        )
    return 0


def cmd_detect(args: argparse.Namespace) -> int:
    service = _service(args)
    document = service.read_document(args.path)
    match = service.detect_provider(document)
    _print_json(
        {
            "provider_id": match.provider_id,
            "provider_name": match.provider_name,
            "confidence": match.confidence,
            "matched_terms": list(match.matched_terms),
            "missing_terms": list(match.missing_terms),
            "rejected_terms": list(match.rejected_terms),
        }
    )
    return 0 if match.provider_id else 4


def cmd_extract(args: argparse.Namespace) -> int:
    service = _service(args)
    document, record = service.process_document(args.path, provider_selector=args.provider)
    payload = {"document": service.document_to_dict(document), "record": service.record_to_dict(record)}
    _print_json(payload if args.include_document else payload["record"])
    missing_required = [
        key
        for key in (
            FieldKey.WORK_PROVIDER,
            FieldKey.VRM,
            FieldKey.VEHICLE_MODEL,
            FieldKey.CLAIMANT_NAME,
            FieldKey.REFERENCE,
            FieldKey.INCIDENT_DATE,
            FieldKey.INSTRUCTION_DATE,
        )
        if not record.fields.get(key) or not record.fields[key].value.strip()
    ]
    return 5 if missing_required and args.fail_on_missing else 0


def cmd_process(args: argparse.Namespace) -> int:
    service = _service(args)
    explicit_out_dir = Path(args.out_dir) if args.out_dir else None
    results = []
    failures = 0
    paths = _expand_paths(args.paths, recursive=args.recursive)
    records_dir = Path(args.records_dir) if args.records_dir else None
    if records_dir:
        records_dir.mkdir(parents=True, exist_ok=True)
    for path in paths:
        try:
            _, record = service.process_document(path, provider_selector=args.provider, engineer_report=args.engineer_report)
            record_dict = service.record_to_dict(record)
            created: list[str] = []
            output_folder = explicit_out_dir
            if output_folder is None and (args.json or args.images):
                output_folder = service.create_output_subfolder(record)
            if args.json:
                created.append(str(service.export_json(record, output_folder)))
            if args.docx:
                created.append(str(service.export_docx(record, explicit_out_dir)))
            if args.images:
                fields = {key.value: value.value for key, value in record.fields.items()}
                created.extend(service.extract_images(path, path.name, fields, output_folder).get("paths", []))
            record_json_path = None
            if records_dir:
                record_json_path = records_dir / f"{_source_stem(path)}.record.json"
                record_json_path.write_text(json.dumps(record_dict, indent=2, ensure_ascii=False), encoding="utf-8")
                created.append(str(record_json_path))
            results.append(
                {
                    "path": str(path),
                    "record": record_dict,
                    "created": created,
                    "output_folder": str(output_folder) if output_folder else None,
                }
            )
        except Exception as exc:
            failures += 1
            results.append({"path": str(path), "error": f"{type(exc).__name__}: {exc}"})
    _print_json(results[0] if len(results) == 1 else {"results": results})
    return 1 if failures else 0


def cmd_providers(args: argparse.Namespace) -> int:
    service = _service(args)
    providers = service.load_providers()
    if args.providers_command == "list":
        _print_json(
            [
                {
                    "id": p.get("id"),
                    "name": p.get("name"),
                    "work_provider": p.get("work_provider"),
                    "enabled": p.get("enabled", True),
                    "priority": p.get("priority", 0),
                    "required_phrases_count": len(p.get("detect", {}).get("required_phrases", [])),
                }
                for p in providers
            ]
        )
        return 0
    if args.providers_command == "show":
        provider = service.provider_by_id_or_name(args.selector, providers)
        if not provider:
            print(f"Provider not found: {args.selector}", file=sys.stderr)
            return 2
        _print_json(provider)
        return 0
    if args.providers_command == "export":
        payload = {"schema_version": 2, "providers": providers}
        if args.path:
            Path(args.path).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        else:
            _print_json(payload)
        return 0
    if args.providers_command == "import":
        with open(args.path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        if payload.get("schema_version", 1) < 2:
            from cedocumentmapper_v2.config import migrate_providers_config

            payload = migrate_providers_config(payload)
        incoming = payload.get("providers", [])
        if args.replace:
            merged = incoming
        else:
            by_id = {p.get("id"): p for p in providers}
            for provider in incoming:
                by_id[provider.get("id")] = provider
            merged = list(by_id.values())
        service.save_provider_catalog(merged)
        _print_json({"imported": len(incoming), "total": len(merged)})
        return 0
    if args.providers_command == "set":
        provider = service.provider_by_id_or_name(args.selector, providers)
        if not provider:
            print(f"Provider not found: {args.selector}", file=sys.stderr)
            return 2
        for attr in ("name", "work_provider", "priority", "enabled"):
            value = getattr(args, attr, None)
            if value is not None:
                provider[attr] = value
        service.save_provider_catalog(providers)
        _print_json(provider)
        return 0
    if args.providers_command == "delete":
        if not args.yes:
            print("Refusing to delete without --yes.", file=sys.stderr)
            return 2
        remaining = [p for p in providers if p.get("id") != args.selector and p.get("name") != args.selector]
        if len(remaining) == len(providers):
            print(f"Provider not found: {args.selector}", file=sys.stderr)
            return 2
        service.save_provider_catalog(remaining)
        _print_json({"deleted": args.selector, "total": len(remaining)})
        return 0
    return 2


def cmd_rules(args: argparse.Namespace) -> int:
    service = _service(args)
    providers = service.load_providers()
    provider = service.provider_by_id_or_name(args.provider, providers)
    if not provider:
        print(f"Provider not found: {args.provider}", file=sys.stderr)
        return 2
    field = FieldKey(args.field)
    field_rules = provider.setdefault("field_rules", {})
    if args.rules_command == "show":
        _print_json(field_rules.get(field.value, {}))
        return 0
    if args.rules_command == "set":
        rule = dict(field_rules.get(field.value, {"id": f"{provider['id']}_{field.value}"}))
        rule["kind"] = args.kind
        if args.labels:
            rule["labels"] = [item.strip() for item in args.labels.split(",") if item.strip()]
        for attr in ("start_label", "end_label", "pattern", "value", "absent_value"):
            value = getattr(args, attr, None)
            if value is not None:
                rule[attr] = value
        if args.tokens:
            rule["tokens"] = [item.strip() for item in args.tokens.split(",") if item.strip()]
        for attr in ("line_number", "line_start", "line_end", "offset"):
            value = getattr(args, attr, None)
            if value is not None:
                rule[attr] = value
        field_rules[field.value] = rule
        service.save_provider_catalog(providers)
        _print_json(rule)
        return 0
    if args.rules_command == "run":
        document = service.read_document(args.path)
        rule = field_rules.get(field.value)
        if not rule:
            print(f"No rule configured for {field.value}", file=sys.stderr)
            return 2
        extraction = RuleEngine().extract_field(document, field, rule)
        _print_json(service.record_to_dict(service.rule_engine.extract_record(document, provider))["fields"][field.value] if args.normalized else {
            "value": extraction.value,
            "raw_value": extraction.raw_value,
            "rule_id": extraction.rule_id,
            "confidence": extraction.confidence,
        })
        return 0
    return 2


def cmd_export(args: argparse.Namespace) -> int:
    service = _service(args)
    out_dir = Path(args.out_dir) if args.out_dir else None
    if args.record:
        payload = json.loads(Path(args.record).read_text(encoding="utf-8"))
        fields = payload.get("fields", payload)
        record = service.record_from_field_map({k: v.get("value", v) if isinstance(v, dict) else v for k, v in fields.items()})
    else:
        _, record = service.process_document(args.path, provider_selector=args.provider)
    if args.export_command == "json":
        result = service.export_json_bundle(record, out_dir)
        _print_json({"created": result["path"], "folder": result["folder"]})
    else:
        path = service.export_docx(record, out_dir)
        _print_json({"created": str(path), "folder": str(path.parent)})
    return 0


def cmd_images(args: argparse.Namespace) -> int:
    service = _service(args)
    _, record = service.process_document(args.path, provider_selector=args.provider)
    fields = {key.value: value.value for key, value in record.fields.items()}
    fields.update({k: v for k, v in {"work_provider": args.work_provider, "vrm": args.vrm}.items() if v})
    _print_json(service.extract_images(args.path, Path(args.path).name, fields, Path(args.out_dir) if args.out_dir else None))
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    service = _service(args)
    paths = _expand_paths(args.paths, recursive=args.recursive)
    out_dir = Path(args.out_dir)
    records_dir = out_dir / "records"
    texts_dir = out_dir / "texts"
    records_dir.mkdir(parents=True, exist_ok=True)
    texts_dir.mkdir(parents=True, exist_ok=True)
    results = []
    failures = 0
    for path in paths:
        try:
            document, record = service.process_document(path, provider_selector=args.provider)
            record_dict = service.record_to_dict(record)
            record_path = records_dir / f"{_source_stem(path)}.record.json"
            text_path = texts_dir / f"{_source_stem(path)}.txt"
            record_path.write_text(json.dumps(record_dict, indent=2, ensure_ascii=False), encoding="utf-8")
            text_path.write_text(document.plain_text, encoding="utf-8")
            results.append(
                {
                    "path": str(path),
                    "record_json": str(record_path),
                    "text": str(text_path),
                    "provider": record.provider.provider_id,
                    "fields": {key: value["value"] for key, value in record_dict["fields"].items()},
                    "issues": _audit_record(record_dict),
                }
            )
        except Exception as exc:
            failures += 1
            results.append({"path": str(path), "error": f"{type(exc).__name__}: {exc}"})
    summary = {"count": len(paths), "failures": failures, "results": results}
    summary_path = out_dir / "audit-summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    _print_json({"summary": str(summary_path), "count": len(paths), "failures": failures})
    return 1 if failures else 0


def _audit_record(record_dict: dict[str, Any]) -> list[str]:
    fields = {key: value.get("value", "") for key, value in record_dict.get("fields", {}).items()}
    issues: list[str] = []
    vrm = fields.get("vrm", "").strip().upper()
    model = fields.get("vehicle_model", "").strip().upper()
    if vrm and model and vrm.replace(" ", "") in model.replace(" ", ""):
        issues.append("vehicle_model_contains_vrm")
    for key in ("claimant_name", "vehicle_model", "reference"):
        value = fields.get(key, "").strip().lower()
        if value in {"name", "model", "reference", "ref", "vehicle", "claimant"}:
            issues.append(f"{key}_looks_like_label")
    for key in ("incident_date", "instruction_date", "inspection_date"):
        value = fields.get(key, "").strip()
        if value and not __import__("re").match(r"^\d{2}/\d{2}/\d{4}$", value):
            issues.append(f"{key}_not_normalized_date")
    return issues


def cmd_version(args: argparse.Namespace) -> int:
    checks = {"python": platform.python_version(), "platform": platform.platform()}
    for module in ("fitz", "pypdf", "docx", "extract_msg", "pytesseract", "webview"):
        try:
            __import__(module)
            checks[module] = "available"
        except Exception as exc:
            checks[module] = f"unavailable: {exc}"
    _print_json(checks)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cedocumentmapper")
    parser.add_argument("--app-data-dir", help="Override CE Document Mapper app data directory.")
    sub = parser.add_subparsers(dest="command", required=True)

    gui = sub.add_parser("gui")
    gui.add_argument("--dev", action="store_true")
    gui.add_argument("--debug", action="store_true")
    gui.set_defaults(func=cmd_gui)

    read = sub.add_parser("read")
    read.add_argument("path")
    read.add_argument("--json", action="store_true")
    read.add_argument("--plain-text", action="store_true")
    read.set_defaults(func=cmd_read)

    detect = sub.add_parser("detect")
    detect.add_argument("path")
    detect.set_defaults(func=cmd_detect)

    extract = sub.add_parser("extract")
    extract.add_argument("path")
    extract.add_argument("--provider")
    extract.add_argument("--include-document", action="store_true")
    extract.add_argument("--fail-on-missing", action="store_true")
    extract.set_defaults(func=cmd_extract)

    process = sub.add_parser("process")
    process.add_argument("paths", nargs="+")
    process.add_argument("--provider")
    process.add_argument("--engineer-report")
    process.add_argument("--json", action="store_true")
    process.add_argument("--docx", action="store_true")
    process.add_argument("--images", action="store_true")
    process.add_argument("--out-dir")
    process.add_argument("--records-dir")
    process.add_argument("--recursive", action="store_true")
    process.set_defaults(func=cmd_process)

    providers = sub.add_parser("providers")
    providers_sub = providers.add_subparsers(dest="providers_command", required=True)
    providers_sub.add_parser("list").set_defaults(func=cmd_providers)
    providers_show = providers_sub.add_parser("show")
    providers_show.add_argument("selector")
    providers_show.set_defaults(func=cmd_providers)
    providers_export = providers_sub.add_parser("export")
    providers_export.add_argument("--path")
    providers_export.set_defaults(func=cmd_providers)
    providers_import = providers_sub.add_parser("import")
    providers_import.add_argument("path")
    providers_import.add_argument("--replace", action="store_true")
    providers_import.set_defaults(func=cmd_providers)
    providers_set = providers_sub.add_parser("set")
    providers_set.add_argument("selector")
    providers_set.add_argument("--name")
    providers_set.add_argument("--work-provider")
    providers_set.add_argument("--priority", type=int)
    providers_set.add_argument("--enabled", type=lambda value: value.lower() in {"1", "true", "yes", "y"})
    providers_set.set_defaults(func=cmd_providers)
    providers_delete = providers_sub.add_parser("delete")
    providers_delete.add_argument("selector")
    providers_delete.add_argument("--yes", action="store_true")
    providers_delete.set_defaults(func=cmd_providers)

    rules = sub.add_parser("rules")
    rules.add_argument("--provider", required=True)
    rules.add_argument("--field", required=True, choices=[key.value for key in FieldKey])
    rules_sub = rules.add_subparsers(dest="rules_command", required=True)
    rules_sub.add_parser("show").set_defaults(func=cmd_rules)
    rules_set = rules_sub.add_parser("set")
    rules_set.add_argument("--kind", required=True)
    rules_set.add_argument("--labels")
    rules_set.add_argument("--start-label")
    rules_set.add_argument("--end-label")
    rules_set.add_argument("--line-number", type=int)
    rules_set.add_argument("--line-start", type=int)
    rules_set.add_argument("--line-end", type=int)
    rules_set.add_argument("--offset", type=int)
    rules_set.add_argument("--pattern")
    rules_set.add_argument("--tokens")
    rules_set.add_argument("--value")
    rules_set.add_argument("--absent-value")
    rules_set.set_defaults(func=cmd_rules)
    rules_run = rules_sub.add_parser("run")
    rules_run.add_argument("path")
    rules_run.add_argument("--normalized", action="store_true")
    rules_run.set_defaults(func=cmd_rules)

    export = sub.add_parser("export")
    export_sub = export.add_subparsers(dest="export_command", required=True)
    for name in ("json", "docx"):
        export_cmd = export_sub.add_parser(name)
        export_cmd.add_argument("path", nargs="?")
        export_cmd.add_argument("--record")
        export_cmd.add_argument("--provider")
        export_cmd.add_argument("--out-dir")
        export_cmd.set_defaults(func=cmd_export)

    images = sub.add_parser("images")
    images_sub = images.add_subparsers(dest="images_command", required=True)
    images_extract = images_sub.add_parser("extract")
    images_extract.add_argument("path")
    images_extract.add_argument("--provider")
    images_extract.add_argument("--work-provider")
    images_extract.add_argument("--vrm")
    images_extract.add_argument("--out-dir")
    images_extract.set_defaults(func=cmd_images)

    audit = sub.add_parser("audit")
    audit.add_argument("paths", nargs="+")
    audit.add_argument("--out-dir", required=True)
    audit.add_argument("--provider")
    audit.add_argument("--recursive", action="store_true")
    audit.set_defaults(func=cmd_audit)

    version = sub.add_parser("version")
    version.set_defaults(func=cmd_version)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
