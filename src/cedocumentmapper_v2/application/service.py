from __future__ import annotations

import io
import json
import shutil
import subprocess
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, cast

from cedocumentmapper_v2.config import migrate_providers_config
from cedocumentmapper_v2.detection import ProviderDetector
from cedocumentmapper_v2.domain.models import (
    DocumentLine,
    DocumentModel,
    DocumentPage,
    ExtractedRecord,
    FieldExtraction,
    FieldKey,
    ProviderMatch,
)
from cedocumentmapper_v2.exporters import EVAJsonExporter, RJSDocxExporter
from cedocumentmapper_v2.readers import get_reader_for_path
from cedocumentmapper_v2.rules import RuleEngine
from cedocumentmapper_v2.ui.paths import APP_DATA_DIR, get_documents_dir, safe_filename, unique_output_path


class DocumentMapperService:
    """Shared use-case layer for document reading, extraction, export, and image work."""

    def __init__(self, app_data_dir: Path | None = None, seed_path: Path | None = None) -> None:
        self.app_data_dir = app_data_dir or APP_DATA_DIR
        self.seed_path = seed_path or Path("providers.json")
        self.config_path = self.app_data_dir / "providers.json"
        self.detector = ProviderDetector()
        self.rule_engine = RuleEngine()

    def load_provider_catalog(self) -> dict[str, Any]:
        if not self.config_path.exists():
            self._seed_providers_file()
        with open(self.config_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if data.get("schema_version", 1) < 2:
            data = migrate_providers_config(data)
            self.save_provider_catalog(data.get("providers", []))
        return cast(dict[str, Any], data)

    def load_providers(self) -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], self.load_provider_catalog().get("providers", []))

    def save_provider_catalog(self, providers: list[dict[str, Any]]) -> None:
        self.app_data_dir.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as fh:
            json.dump({"schema_version": 2, "providers": providers}, fh, indent=2)

    def read_document(self, path: str | Path) -> DocumentModel:
        path_obj = Path(path)
        return get_reader_for_path(path_obj).read(path_obj)

    def detect_provider(self, document: DocumentModel, providers: list[dict[str, Any]] | None = None) -> ProviderMatch:
        return self.detector.detect(document, providers or self.load_providers())

    def provider_by_id_or_name(self, selector: str, providers: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
        haystack = providers or self.load_providers()
        selector_lower = selector.lower()
        return next(
            (
                provider
                for provider in haystack
                if str(provider.get("id", "")).lower() == selector_lower
                or str(provider.get("name", "")).lower() == selector_lower
                or str(provider.get("work_provider", "")).lower() == selector_lower
            ),
            None,
        )

    def extract_document(
        self,
        document: DocumentModel,
        provider: dict[str, Any] | None = None,
        providers: list[dict[str, Any]] | None = None,
    ) -> ExtractedRecord:
        provider_cfg = provider
        if provider_cfg is None:
            loaded = providers or self.load_providers()
            match = self.detect_provider(document, loaded)
            provider_cfg = next((p for p in loaded if p.get("id") == match.provider_id), None)
            if provider_cfg is None:
                provider_cfg = {
                    "id": "unknown_temp",
                    "name": "New Provider (Auto-Detected)",
                    "work_provider": "UNKNOWN",
                    "enabled": True,
                    "priority": 999,
                    "detect": {
                        "required_phrases": [],
                        "optional_phrases": [],
                        "negative_phrases": [],
                        "minimum_confidence": 0.0
                    },
                    "field_rules": {}
                }
        if provider_cfg is None:
            return ExtractedRecord(provider=ProviderMatch(None, "Unknown", 0.0), fields={})
        return self.rule_engine.extract_record(document, provider_cfg)

    def process_document(
        self,
        path: str | Path,
        provider_selector: str | None = None,
        engineer_report: str | Path | None = None,
    ) -> tuple[DocumentModel, ExtractedRecord]:
        providers = self.load_providers()
        document = self.read_document(path)
        provider = self.provider_by_id_or_name(provider_selector, providers) if provider_selector else None
        record = self.extract_document(document, provider, providers)
        if engineer_report is not None:
            _, engineer_record = self.process_document(engineer_report, provider_selector)
            record = self.overlay_records(record, engineer_record)
        return document, record

    def overlay_records(self, base: ExtractedRecord, engineer: ExtractedRecord) -> ExtractedRecord:
        merged = dict(base.fields)
        for key, extraction in engineer.fields.items():
            if key == FieldKey.WORK_PROVIDER:
                continue
            if extraction.value.strip():
                merged[key] = extraction
        return ExtractedRecord(provider=base.provider, fields=merged, issues=base.issues + engineer.issues)

    def export_json(self, record: ExtractedRecord, out_dir: Path | None = None) -> Path:
        json_text = EVAJsonExporter().export(record)
        path = self._output_path(record, ".json", out_dir)
        path.write_text(json_text, encoding="utf-8")
        return path

    def export_json_bundle(self, record: ExtractedRecord, out_dir: Path | None = None) -> dict[str, Any]:
        folder = out_dir or self.create_output_subfolder(record)
        path = self.export_json(record, folder)
        return {"path": str(path), "folder": str(folder)}

    def export_docx(self, record: ExtractedRecord, out_dir: Path | None = None) -> Path:
        docx_bytes = RJSDocxExporter().export(record)
        path = self._output_path(record, ".docx", out_dir)
        path.write_bytes(docx_bytes)
        return path

    def extract_images(
        self,
        source: str | Path | bytes,
        source_name: str,
        fields: dict[str, str],
        out_dir: Path | None = None,
    ) -> dict[str, Any]:
        data = Path(source).read_bytes() if isinstance(source, (str, Path)) else source
        ext = Path(source_name).suffix.lower()
        output_dir = out_dir or self.create_output_subfolder_from_fields(fields)
        output_dir.mkdir(parents=True, exist_ok=True)
        base_name = f"{safe_filename(fields.get('work_provider', 'RJS'))}_{safe_filename(fields.get('vrm', '') or 'UnknownVRM')}"
        saved: list[Path] = []
        notes: list[str] = []

        def save_bytes(stem: str, suffix: str, content: bytes) -> None:
            path = unique_output_path(output_dir, stem, suffix)
            path.write_bytes(content)
            saved.append(path)

        def extract_docx_media(docx_bytes: bytes) -> None:
            with zipfile.ZipFile(io.BytesIO(docx_bytes), "r") as zf:
                media = [name for name in zf.namelist() if name.startswith("word/media/") and not name.endswith("/")]
                for idx, member in enumerate(media, start=1):
                    suffix = Path(member).suffix or ".bin"
                    save_bytes(f"{base_name}_img_{idx}", suffix, zf.read(member))

        if ext == ".pdf":
            try:
                import fitz

                doc = fitz.open(stream=data, filetype="pdf")
                try:
                    idx = 1
                    for page_num, page in enumerate(doc, start=1):
                        for img_info in page.get_images() or []:
                            base_image = doc.extract_image(img_info[0])
                            if base_image:
                                save_bytes(f"{base_name}_img_{page_num}_{idx}", "." + base_image["ext"], base_image["image"])
                                idx += 1
                finally:
                    doc.close()
            except Exception as exc:
                try:
                    from pypdf import PdfReader

                    reader = PdfReader(io.BytesIO(data))
                    idx = 1
                    for page_num, page in enumerate(reader.pages, start=1):
                        for image in getattr(page, "images", []) or []:
                            suffix = Path(getattr(image, "name", "")).suffix or ".bin"
                            save_bytes(f"{base_name}_img_{page_num}_{idx}", suffix, image.data)
                            idx += 1
                except Exception as pypdf_exc:
                    notes.append(f"PDF image extraction failed: {exc} / {pypdf_exc}")
        elif ext == ".docx":
            extract_docx_media(data)
        elif ext == ".doc":
            with tempfile.TemporaryDirectory() as tmpdir:
                temp_dir = Path(tmpdir)
                temp_doc = temp_dir / source_name
                temp_doc.write_bytes(data)
                converted = self._convert_doc_to_docx(temp_doc, temp_dir, notes)
                if converted:
                    extract_docx_media(converted.read_bytes())
                else:
                    notes.append("Could not convert DOC for image extraction.")
        else:
            notes.append("Image extraction is only supported for PDF, DOCX, and DOC.")

        return {
            "success": bool(saved),
            "count": len(saved),
            "paths": [str(path) for path in saved],
            "folder": str(output_dir),
            "message": f"Successfully extracted {len(saved)} image(s)." if saved else "No images extracted. " + " ".join(notes),
        }

    def create_output_subfolder(self, record: ExtractedRecord) -> Path:
        fields = {key.value: value.value for key, value in record.fields.items()}
        return self.create_output_subfolder_from_fields(fields)

    def create_output_subfolder_from_fields(self, fields: dict[str, str]) -> Path:
        root = get_documents_dir() / "cedocumentmapper_outputs"
        root.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        work_provider = safe_filename(fields.get("work_provider", "") or "UnknownProvider")
        vrm = safe_filename(fields.get("vrm", "") or "UnknownVRM")
        return unique_output_path(root, f"{timestamp}_{work_provider}_{vrm}", "")

    def _convert_doc_to_docx(self, source: Path, out_dir: Path, notes: list[str]) -> Path | None:
        target = out_dir / f"{source.stem}.docx"
        try:
            import pythoncom
            import win32com.client

            pythoncom.CoInitialize()
            word = win32com.client.Dispatch("Word.Application")
            word.Visible = False
            try:
                doc = word.Documents.Open(str(source.resolve()))
                doc.SaveAs2(str(target.resolve()), FileFormat=16)
                doc.Close()
            finally:
                word.Quit()
                pythoncom.CoUninitialize()
            if target.exists():
                return target
        except Exception as exc:
            notes.append(f"Word COM DOC conversion failed: {exc}")

        soffice = shutil.which("soffice") or shutil.which("libreoffice")
        if not soffice:
            notes.append("LibreOffice not available for DOC conversion.")
            return None
        try:
            subprocess.run(
                [soffice, "--headless", "--convert-to", "docx", "--outdir", str(out_dir), str(source.resolve())],
                check=True,
                capture_output=True,
                timeout=30,
            )
            return next(iter(out_dir.glob("*.docx")), None)
        except Exception as exc:
            notes.append(f"LibreOffice DOC conversion failed: {exc}")
            return None

    def record_from_field_map(self, fields: dict[str, str]) -> ExtractedRecord:
        record_fields = {
            FieldKey(key): FieldExtraction(value=value)
            for key, value in fields.items()
            if key in {field.value for field in FieldKey}
        }
        return ExtractedRecord(
            provider=ProviderMatch(None, fields.get("work_provider", ""), 1.0),
            fields=record_fields,
        )

    def document_to_dict(self, doc: DocumentModel) -> dict[str, Any]:
        return {
            "source_path": str(doc.source_path),
            "source_type": doc.source_type,
            "plain_text": doc.plain_text,
            "reader_notes": list(doc.reader_notes),
            "metadata": doc.metadata,
            "pages": [
                {
                    "page_index": page.page_index,
                    "width": page.width,
                    "height": page.height,
                    "lines": [
                        {
                            "text": line.text,
                            "page_index": line.page_index,
                            "line_index": line.line_index,
                            "bbox": list(line.bbox) if line.bbox else None,
                            "block_id": line.block_id,
                            "confidence": line.confidence,
                        }
                        for line in page.lines
                    ],
                }
                for page in doc.pages
            ],
        }

    def document_from_dict(self, data: dict[str, Any]) -> DocumentModel:
        pages = []
        for page_data in data.get("pages", []):
            lines = [
                DocumentLine(
                    text=line["text"],
                    page_index=line["page_index"],
                    line_index=line["line_index"],
                    bbox=tuple(line["bbox"]) if line.get("bbox") else None,
                    block_id=line.get("block_id"),
                    confidence=line.get("confidence"),
                )
                for line in page_data.get("lines", [])
            ]
            pages.append(
                DocumentPage(
                    page_index=page_data["page_index"],
                    width=page_data.get("width"),
                    height=page_data.get("height"),
                    lines=tuple(lines),
                )
            )
        return DocumentModel(
            source_path=Path(data.get("source_path", "")),
            source_type=cast(Literal["pdf", "docx", "doc", "eml", "msg", "txt"], data.get("source_type", "pdf")),
            pages=tuple(pages),
            plain_text=data.get("plain_text", ""),
            reader_notes=tuple(data.get("reader_notes", [])),
            metadata=data.get("metadata", {}),
        )

    def record_to_dict(self, record: ExtractedRecord) -> dict[str, Any]:
        return {
            "provider": {
                "provider_id": record.provider.provider_id,
                "provider_name": record.provider.provider_name,
                "confidence": record.provider.confidence,
                "matched_terms": list(record.provider.matched_terms),
                "missing_terms": list(record.provider.missing_terms),
                "rejected_terms": list(record.provider.rejected_terms),
            },
            "fields": {
                key.value: {
                    "value": value.value,
                    "raw_value": value.raw_value,
                    "rule_id": value.rule_id,
                    "confidence": value.confidence,
                    "source_span": {
                        "page_index": value.source_span.page_index,
                        "line_index": value.source_span.line_index,
                        "bbox": list(value.source_span.bbox) if value.source_span.bbox else None,
                    }
                    if value.source_span
                    else None,
                    "issues": [
                        {
                            "field": issue.field.value if issue.field else None,
                            "severity": issue.severity,
                            "code": issue.code,
                            "message": issue.message,
                        }
                        for issue in value.issues
                    ],
                }
                for key, value in record.fields.items()
            },
            "issues": [
                {
                    "field": issue.field.value if issue.field else None,
                    "severity": issue.severity,
                    "code": issue.code,
                    "message": issue.message,
                }
                for issue in record.issues
            ],
        }

    def _output_path(self, record: ExtractedRecord, extension: str, out_dir: Path | None) -> Path:
        directory = out_dir or self.create_output_subfolder(record)
        directory.mkdir(parents=True, exist_ok=True)
        work_provider = record.fields.get(FieldKey.WORK_PROVIDER, FieldExtraction("")).value
        vrm = record.fields.get(FieldKey.VRM, FieldExtraction("")).value or "UnknownVRM"
        return unique_output_path(directory, f"{safe_filename(work_provider)}_{safe_filename(vrm)}", extension)

    def _seed_providers_file(self) -> None:
        self.app_data_dir.mkdir(parents=True, exist_ok=True)
        candidates = [
            self.seed_path,
            Path(__file__).resolve().parents[3] / "providers.json",
        ]
        for candidate in candidates:
            if candidate.exists():
                shutil.copy2(candidate, self.config_path)
                return
        self.save_provider_catalog(
            [
                {
                    "id": "rjs",
                    "name": "RJS Solicitors",
                    "work_provider": "RJS",
                    "enabled": True,
                    "priority": 1,
                    "detect": {"required_phrases": ["RJS Solicitors"], "optional_phrases": [], "negative_phrases": [], "minimum_confidence": 0.8},
                    "field_rules": {},
                }
            ]
        )
