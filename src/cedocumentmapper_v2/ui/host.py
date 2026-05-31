from __future__ import annotations

import sys
import json
import webview
from pathlib import Path
from typing import Any, Literal, Optional, cast, TYPE_CHECKING

if TYPE_CHECKING:
    from cedocumentmapper_v2.domain.models import DocumentModel, ExtractedRecord

from cedocumentmapper_v2.ui.paths import (
    APP_DATA_DIR,
    get_desktop_dir,
    safe_filename,
    unique_output_path,
)
from cedocumentmapper_v2.application import DocumentMapperService

class WebviewBridge:
    def __init__(self) -> None:
        self.service = DocumentMapperService()
        self.window: Optional[webview.Window] = None
        self.last_detected_provider_id: Optional[str] = None
        self.last_imported_bytes: Optional[bytes] = None
        self.last_imported_path: Optional[str] = None
        self.last_imported_name: Optional[str] = None

    def load_providers(self) -> list[dict[str, Any]]:
        try:
            return self.service.load_providers()
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def save_providers(self, providers: list[dict[str, Any]]) -> bool:
        try:
            self.service.save_provider_catalog(providers)
            return True
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def import_file(self, path: str, is_engineer_report: bool = False) -> dict[str, Any]:
        try:
            path_obj = Path(path)
            doc_model, record = self.service.process_document(path_obj)
            
            if not is_engineer_report:
                self.last_imported_bytes = None
                self.last_imported_path = path
                self.last_imported_name = path_obj.name

            match = record.provider
            if match.provider_id and not is_engineer_report:
                self.last_detected_provider_id = match.provider_id

            if is_engineer_report and self.last_detected_provider_id:
                provider_cfg = self.service.provider_by_id_or_name(self.last_detected_provider_id)
                if provider_cfg:
                    record = self.service.extract_document(doc_model, provider_cfg)
            else:
                provider_cfg = self.service.provider_by_id_or_name(match.provider_id or "") if match.provider_id else None
                if not is_engineer_report:
                    self.last_detected_provider_id = match.provider_id

            pdf_path = path_obj.resolve().as_uri() if path_obj.suffix.lower() == ".pdf" else None

            return {
                "document": self.service.document_to_dict(doc_model),
                "record": self.service.record_to_dict(record),
                "pdf_base64": None,
                "pdf_path": pdf_path,
            }
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def import_file_data(self, name: str, base64_data: str, is_engineer_report: bool = False) -> dict[str, Any]:
        try:
            import base64
            import tempfile
            from pathlib import Path
            
            file_bytes = base64.b64decode(base64_data)
            suffix = Path(name).suffix
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                temp_file.write(file_bytes)
                temp_path = temp_file.name
                
            try:
                res = self.import_file(temp_path, is_engineer_report)
                res["document"]["source_path"] = name
                if suffix == ".pdf":
                    res["pdf_base64"] = base64_data
                
                if not is_engineer_report:
                    self.last_imported_bytes = file_bytes
                    self.last_imported_path = None
                    self.last_imported_name = name
                return res
            finally:
                try:
                    Path(temp_path).unlink()
                except Exception:
                    pass
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e


    def re_run_rule(self, doc_text: str, file_type: str, lines: list[dict[str, Any]], rule: dict[str, Any], field_key: str) -> dict[str, Any]:
        try:
            from cedocumentmapper_v2.domain.models import DocumentLine, DocumentPage, DocumentModel, FieldKey, FieldExtraction
            from cedocumentmapper_v2.rules import RuleEngine
            from cedocumentmapper_v2.normalization import (
                normalize_vrm,
                normalize_mileage,
                normalize_date,
                normalize_vat_status,
                normalize_mileage_unit,
                normalize_address,
            )

            doc_lines = []
            for l in lines:
                bbox_val = tuple(l["bbox"]) if l.get("bbox") else None
                doc_lines.append(
                    DocumentLine(
                        text=l["text"],
                        page_index=l["page_index"],
                        line_index=l["line_index"],
                        bbox=bbox_val,
                        block_id=l.get("block_id"),
                        confidence=l.get("confidence")
                    )
                )
            
            pages_map: dict[int, list[DocumentLine]] = {}
            for line in doc_lines:
                pages_map.setdefault(line.page_index, []).append(line)
            
            pages = []
            for p_idx, p_lines in sorted(pages_map.items()):
                pages.append(
                    DocumentPage(
                        page_index=p_idx,
                        lines=tuple(p_lines)
                    )
                )
                
            doc = DocumentModel(
                source_path=Path("sandbox_temp"),
                source_type=file_type, # type: ignore
                pages=tuple(pages),
                plain_text=doc_text
            )
            
            rule_engine = RuleEngine()
            fk = FieldKey(field_key)
            ext = rule_engine.extract_field(doc, fk, rule)
            
            norm_val = ext.value
            if fk == FieldKey.VRM:
                norm_val = normalize_vrm(norm_val)
            elif fk == FieldKey.MILEAGE:
                norm_val = normalize_mileage(norm_val)
            elif fk in {FieldKey.INCIDENT_DATE, FieldKey.INSTRUCTION_DATE, FieldKey.INSPECTION_DATE}:
                norm_val = normalize_date(norm_val)
            elif fk == FieldKey.VAT_STATUS:
                norm_val = normalize_vat_status(norm_val)
            elif fk == FieldKey.MILEAGE_UNIT:
                norm_val = normalize_mileage_unit(norm_val)
            elif fk == FieldKey.INSPECTION_ADDRESS:
                norm_val = normalize_address(norm_val, force_postcode=False)
                
            ext_normalized = FieldExtraction(
                value=norm_val,
                raw_value=ext.raw_value,
                rule_id=ext.rule_id,
                confidence=ext.confidence,
                source_span=ext.source_span,
                issues=ext.issues
            )
            
            return {
                "value": ext_normalized.value,
                "raw_value": ext_normalized.raw_value,
                "rule_id": ext_normalized.rule_id,
                "confidence": ext_normalized.confidence,
                "source_span": {
                    "page_index": ext_normalized.source_span.page_index,
                    "line_index": ext_normalized.source_span.line_index,
                    "bbox": list(ext_normalized.source_span.bbox) if ext_normalized.source_span.bbox else None
                } if ext_normalized.source_span else None,
                "issues": [
                    {
                        "field": iss.field.value if iss.field else None,
                        "severity": iss.severity,
                        "code": iss.code,
                        "message": iss.message
                    }
                    for iss in ext_normalized.issues
                ]
            }
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def extract_document_with_provider(self, doc_dict: dict[str, Any], provider_cfg: dict[str, Any]) -> dict[str, Any]:
        try:
            doc_model = self.service.document_from_dict(doc_dict)
            record = self.service.extract_document(doc_model, provider_cfg)
            return self.service.record_to_dict(record)
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def extract_images(self, fields: dict[str, str]) -> dict[str, Any]:
        try:
            from pathlib import Path

            if getattr(self, "last_imported_bytes", None):
                source = self.last_imported_bytes
                source_name = getattr(self, "last_imported_name", "document")
            elif getattr(self, "last_imported_path", None):
                path_obj = Path(str(self.last_imported_path))
                if path_obj.exists():
                    source = path_obj
                    source_name = path_obj.name
                else:
                    return {"success": False, "message": f"Source file not found on disk: {path_obj}"}
            else:
                return {"success": False, "message": "No document is currently loaded."}

            return self.service.extract_images(source, source_name, fields)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"success": False, "message": f"Error extracting images: {str(e)}"}

    def export_json(self, fields: dict[str, str]) -> dict[str, str]:
        try:
            return self.service.export_json_bundle(self.service.record_from_field_map(fields))
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def open_folder(self, folder_path: str) -> bool:
        try:
            import os
            import subprocess
            import sys

            path = Path(folder_path)
            if not path.exists() or not path.is_dir():
                return False
            if sys.platform == "win32":
                os.startfile(str(path))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
            return True
        except Exception:
            return False

    def export_docx(self, fields: dict[str, str]) -> bool:
        try:
            from cedocumentmapper_v2.domain.models import FieldKey, FieldExtraction, ExtractedRecord, ProviderMatch
            from cedocumentmapper_v2.exporters import RJSDocxExporter
            
            record_fields = {}
            for k_str, val in fields.items():
                record_fields[FieldKey(k_str)] = FieldExtraction(value=val)
            
            record = ExtractedRecord(
                provider=ProviderMatch(
                    provider_id="rjs",
                    provider_name="RJS Solicitors",
                    confidence=1.0
                ),
                fields=record_fields
            )
            
            exporter = RJSDocxExporter()
            docx_bytes = exporter.export(record)
            
            desktop = get_desktop_dir()
            wp_slug = safe_filename(fields.get("work_provider", "RJS"))
            vrm_slug = safe_filename(fields.get("vrm", "") or "UnknownVRM")
            base_name = f"{wp_slug}_{vrm_slug}"
            
            out_path = unique_output_path(desktop, base_name, ".docx")
            out_path.write_bytes(docx_bytes)
            return True
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def select_file_dialog(self) -> Optional[str]:
        if not self.window:
            return None
        file_types = ('Document Files (*.pdf;*.docx;*.doc;*.eml;*.msg)', 'All files (*.*)')
        res = self.window.create_file_dialog(
            dialog_type=webview.OPEN_DIALOG,
            allow_multiple=False,
            file_types=file_types
        )
        if res and len(res) > 0:
            return str(res[0])
        return None

    def _seed_providers_file(self, dest_path: Path) -> None:
        import shutil
        seed_sources = [
            Path("providers.json"),
            Path(__file__).parent.parent.parent.parent / "providers.json",
            Path(sys.argv[0]).parent / "providers.json",
        ]
        if hasattr(sys, "_MEIPASS"):
            seed_sources.append(Path(sys._MEIPASS) / "providers.json")
            
        for src in seed_sources:
            if src.exists():
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest_path)
                return
                
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        default_seed = {
            "schema_version": 2,
            "providers": [
                {
                    "id": "rjs",
                    "name": "RJS Solicitors",
                    "work_provider": "RJS",
                    "enabled": True,
                    "priority": 1,
                    "detect": {
                        "required_phrases": ["RJS Solicitors"],
                        "optional_phrases": [],
                        "negative_phrases": [],
                        "minimum_confidence": 0.8
                    },
                    "field_rules": {}
                }
            ]
        }
        with open(dest_path, "w", encoding="utf-8") as f:
            json.dump(default_seed, f, indent=2)

    def _doc_to_dict(self, doc: DocumentModel) -> dict[str, Any]:
        return {
            "source_path": str(doc.source_path),
            "source_type": doc.source_type,
            "plain_text": doc.plain_text,
            "reader_notes": list(doc.reader_notes),
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
                            "confidence": line.confidence
                        }
                        for line in page.lines
                    ]
                }
                for page in doc.pages
            ]
        }

    def _record_to_dict(self, record: ExtractedRecord) -> dict[str, Any]:
        return {
            "provider": {
                "provider_id": record.provider.provider_id,
                "provider_name": record.provider.provider_name,
                "confidence": record.provider.confidence,
                "matched_terms": list(record.provider.matched_terms),
                "missing_terms": list(record.provider.missing_terms),
                "rejected_terms": list(record.provider.rejected_terms)
            },
            "fields": {
                k.value: {
                    "value": v.value,
                    "raw_value": v.raw_value,
                    "rule_id": v.rule_id,
                    "confidence": v.confidence,
                    "source_span": {
                        "page_index": v.source_span.page_index,
                        "line_index": v.source_span.line_index,
                        "bbox": list(v.source_span.bbox) if v.source_span.bbox else None
                    } if v.source_span else None,
                    "issues": [
                        {
                            "field": iss.field.value if iss.field else None,
                            "severity": iss.severity,
                            "code": iss.code,
                            "message": iss.message
                        }
                        for iss in v.issues
                    ]
                }
                for k, v in record.fields.items()
            },
            "issues": [
                {
                    "field": iss.field.value if iss.field else None,
                    "severity": iss.severity,
                    "code": iss.code,
                    "message": iss.message
                }
                for iss in record.issues
            ]
        }

def start_webview(debug: bool = False) -> None:
    dev_url = "http://localhost:5173"
    
    if debug:
        url = dev_url
    else:
        # Check PyInstaller path first
        if hasattr(sys, "_MEIPASS"):
            prod_path = Path(sys._MEIPASS) / "frontend" / "dist" / "index.html"
        else:
            prod_path = Path(__file__).parent.parent.parent.parent / "frontend" / "dist" / "index.html"
            
        if prod_path.exists():
            url = str(prod_path)
        else:
            url = dev_url
            
    # Initialize the bridge
    bridge = WebviewBridge()
    
    # Create pywebview window
    window = webview.create_window(
        title="CE Document Mapper v2.0",
        url=url,
        js_api=bridge,
        width=1440,
        height=900,
        min_size=(1024, 768),
        background_color="#0b0f19"
    )
    bridge.window = window
    
    # Start webview loop with HTTP server enabled for production to bypass file origin limits
    if debug:
        webview.start(debug=True)
    else:
        webview.start(debug=False, http_server=True)
